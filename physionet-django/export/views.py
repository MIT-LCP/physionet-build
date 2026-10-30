import logging
import os

from django.contrib.auth import SESSION_KEY
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from oauth2_provider.models import AccessToken
from django.urls import reverse
from rest_framework import generics, mixins, status, permissions
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.views import APIView

from project.authorization.access import (
    RequirementStatus,
    can_access_project,
    can_view_project_files,
    get_access_requirements,
    is_region_blocked,
)
from project.models import AccessPolicy, PublishedProject, ProjectType
from project.utility import DOWNLOAD_TOKEN_SCOPE
from export.serializers import (
    PublishedProjectSerializer,
    PublishedProjectDetailSerializer,
    ProjectVersionsSerializer
)
from search.views import get_content

logger = logging.getLogger(__name__)


class StandardRateThrottle(UserRateThrottle):
    """Rate limit for authenticated users"""
    rate = '100/hour'


class StandardAnonRateThrottle(AnonRateThrottle):
    """Rate limit for anonymous users"""
    rate = '20/hour'


class SessionOnlyAuthentication(SessionAuthentication):
    """
    Session authentication that only accepts users logged in through the Django session,
    not users attached to the request by other middleware.
    """
    def authenticate(self, request):
        result = super().authenticate(request)
        if result and str(result[0].pk) != str(request._request.session.get(SESSION_KEY)):
            return None
        return result


class PublishedProjectList(mixins.ListModelMixin, generics.GenericAPIView):
    """
    List all published projects.

    Returns a paginated list of all published projects, ordered by ID.
    Supports filtering by resource type and search terms.

    Response includes:
        - Public project UUID (persistent unique identifier)
        - Basic metadata (title, version, slug, DOIs, etc.)
        - License and DUA information
        - Storage sizes
        - Resource type as descriptive string (e.g., Database, Software, Challenge, Model)
        - Access policy (Open, Restricted, Credentialed, Contributor Review) - as string
        - Topics (list of descriptive keywords)
        - Source URL (full URL to project page)

    Authentication:
        - Session or Basic authentication required
        - Rate limited: 100 requests/hour for authenticated users
        - Rate limited: 20 requests/hour for anonymous users
    """
    queryset = PublishedProject.objects.all().order_by('id').prefetch_related('topics')
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = PublishedProjectSerializer
    throttle_classes = [StandardRateThrottle, StandardAnonRateThrottle]

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class ProjectVersionList(mixins.ListModelMixin, generics.GenericAPIView):
    """
    List all versions of a specific project.

    Returns a list of all versions for a given project slug.

    Parameters:
        project_slug (str): The unique identifier for the project

    Authentication:
        - Session or Basic authentication required
        - Rate limited: 100 requests/hour for authenticated users
        - Rate limited: 20 requests/hour for anonymous users
    """
    serializer_class = ProjectVersionsSerializer
    throttle_classes = [StandardRateThrottle, StandardAnonRateThrottle]

    def get_queryset(self):
        project_slug = self.kwargs.get('project_slug')
        queryset = PublishedProject.objects.filter(slug=project_slug).order_by('id')
        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class PublishedProjectDetail(mixins.RetrieveModelMixin, generics.GenericAPIView):
    """
    Retrieve details of a specific project version.

    Returns detailed information about a specific version of a project.

    Parameters:
        project_slug (str): The unique identifier for the project
        version (str): The version number of the project

    Response includes:
        - Public project UUID (persistent unique identifier)
        - Complete project metadata (title, version, slug, abstract, etc.)
        - License information
        - Project home page
        - DOI
        - Storage sizes
        - Resource type as descriptive string (e.g., Database, Software, Challenge, Model)
        - Access policy (Open, Restricted, Credentialed, Contributor Review) - as string
        - Topics (list of descriptive keywords)
        - Source URL (full URL to project page)

    Authentication:
        - Session or Basic authentication required
        - Rate limited: 100 requests/hour for authenticated users
        - Rate limited: 20 requests/hour for anonymous users
    """
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    throttle_classes = [StandardRateThrottle, StandardAnonRateThrottle]

    def get(self, request, project_slug, version, *args, **kwargs):
        project = get_object_or_404(PublishedProject, slug=project_slug, version=version)
        serializer = PublishedProjectDetailSerializer(project, context={'request': request})
        return Response(serializer.data)


class ProjectAccessStatus(APIView):
    """
    Describe whether the requester can download a published version directly from PhysioNet.

    Use "latest" as the version to resolve the latest published version. The response lists
    the standard access steps and their status. This endpoint is informational: it does not
    grant access, and each file request is authorized separately. Cloud access is separate.

    Response includes:
        - slug, resolved version and access policy
        - authenticated: whether the request was authenticated
        - can_download: the file access decision used for direct downloads, and false
          while the files are under embargo
        - status: ready, sign_in_required, action_required or unavailable
        - reason: why files are unavailable (deprecated_files, embargoed,
          downloads_disabled, region_blocked or other), otherwise null
        - requirements: a list of steps, each with an id (unique in the list), code,
          label, status (complete, pending, required or unknown) and url
        - project_url: full URL to the project page

    Authentication:
        - Session or Basic authentication. OAuth tokens are not accepted, because the
          response reveals credentialing and training status.
        - Rate limited: 100 requests/hour for authenticated users
        - Rate limited: 20 requests/hour for anonymous users
    """
    authentication_classes = [BasicAuthentication, SessionOnlyAuthentication]
    throttle_classes = [StandardRateThrottle, StandardAnonRateThrottle]

    def get(self, request, project_slug, version):
        projects = PublishedProject.objects.filter(slug=project_slug)
        if version == 'latest':
            project = get_object_or_404(projects, is_latest_version=True)
        else:
            project = get_object_or_404(projects, version=version)

        user = request.user
        project_url = request.build_absolute_uri(
            reverse('published_project', args=(project.slug, project.version))
        )
        step_urls = {
            'sign_in': request.build_absolute_uri(reverse('login')),
            'credentialing': request.build_absolute_uri(reverse('edit_credentialing')),
            'training': request.build_absolute_uri(reverse('edit_training')),
            'dua': project_url,
            'review': project_url,
        }
        requirements = get_access_requirements(project, user)
        for item in requirements:
            item['url'] = step_urls[item['code']]

        embargoed = project.embargo_active()
        can_download = not embargoed and can_view_project_files(project, user, request)
        reason = None
        if can_download:
            state = 'ready'
        elif project.deprecated_files:
            state, reason = 'unavailable', 'deprecated_files'
        elif embargoed:
            state, reason = 'unavailable', 'embargoed'
        elif not project.allow_file_downloads:
            state, reason = 'unavailable', 'downloads_disabled'
        elif is_region_blocked(project, request):
            state, reason = 'unavailable', 'region_blocked'
        elif not user.is_authenticated and project.access_policy != AccessPolicy.OPEN:
            state = 'sign_in_required'
        elif any(item['status'] in (RequirementStatus.REQUIRED, RequirementStatus.PENDING)
                 for item in requirements):
            state = 'action_required'
        else:
            # Every step is complete but access is denied, so get_access_requirements and
            # can_access_project disagree. Log it so the mismatch can be fixed.
            logger.warning(
                'Access requirements complete but access denied: project=%s version=%s user=%s policy=%s',
                project.slug, project.version, user.pk, project.access_policy,
            )
            state, reason = 'unavailable', 'other'

        return Response({
            'slug': project.slug,
            'version': project.version,
            'access_policy': project.get_access_policy_display(),
            'authenticated': user.is_authenticated,
            'can_download': can_download,
            'status': state,
            'reason': reason,
            'requirements': requirements,
            'project_url': project_url,
        })


class PublishedProjectSearch(mixins.ListModelMixin, generics.GenericAPIView):
    """
    Search for published projects.

    Search projects using keywords and filter by resource type.

    Query Parameters:
        search_term (str): Keywords to search for in project titles and descriptions
        resource_type (list): List of resource types to filter by (default: ['all'])

    Authentication:
        - Session or Basic authentication required
        - Rate limited: 100 requests/hour for authenticated users
        - Rate limited: 20 requests/hour for anonymous users
    """
    serializer_class = PublishedProjectSerializer
    throttle_classes = [StandardRateThrottle, StandardAnonRateThrottle]

    def check_resource_type(self, resource_type):
        """
        Check if the requested resource types are valid.

        Args:
            resource_type (list): List of resource types to validate

        Returns:
            bool: True if all resource types are valid, False otherwise
        """
        available_resource_types = ProjectType.objects.all().values_list('name', flat=True)
        for r_type in resource_type:
            if r_type != 'all' and r_type.capitalize() not in available_resource_types:
                return False
        return True

    def get_queryset(self):
        """
        Get the queryset based on search parameters.

        Returns:
            QuerySet: Filtered queryset of published projects
        """
        resource_type = self.request.GET.getlist('resource_type', ['all'])
        search_term = self.request.GET.get('search_term', ' ')

        if 'all' in resource_type:
            resource_type_list = ProjectType.objects.all().values_list('name', flat=True)
        else:
            resource_type_list = [x.capitalize() for x in resource_type]

        resource_type_list = ProjectType.objects.filter(name__in=resource_type_list).values_list('id', flat=True)
        queryset = get_content(resource_type_list, 'relevance', 'desc', search_term)

        return queryset

    def get(self, request, *args, **kwargs):
        """
        Handle GET requests for project search.

        Returns:
            Response: List of matching projects or error message
        """
        resource_type = self.request.GET.getlist('resource_type', ['all'])
        if not self.check_resource_type(resource_type):
            return Response(
                {'error': 'Invalid resource_type'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return self.list(request, *args, **kwargs)


class TokenHasDownloadScope(permissions.BasePermission):
    """
    OAuth access tokens must have the download scope. Session and Basic authentication are unaffected.
    """
    def has_permission(self, request, view):
        token = request.auth
        return not isinstance(token, AccessToken) or token.allow_scopes([DOWNLOAD_TOKEN_SCOPE])


class ProjectSHA256Sums(APIView):
    """
    Download SHA256SUMS.txt file for a project.
    """
    permission_classes = [permissions.IsAuthenticated, TokenHasDownloadScope]

    def get(self, request, project_slug, version):
        project = get_object_or_404(PublishedProject, slug=project_slug, version=version)

        # Check if user has access to the project
        if not can_access_project(project, request.user, request):
            return Response({"error": "You do not have permission to access this project"}, status=403)

        # Get the path to SHA256SUMS.txt
        sha256sums_path = os.path.join(project.file_root(), 'SHA256SUMS.txt')

        if not os.path.exists(sha256sums_path):
            return Response({"error": "SHA256SUMS.txt not found for this project"}, status=404)

        # Return the file as a download
        response = FileResponse(open(sha256sums_path, 'rb'))
        response['Content-Type'] = 'text/plain'
        response['Content-Disposition'] = 'attachment; filename="SHA256SUMS.txt"'
        return response
