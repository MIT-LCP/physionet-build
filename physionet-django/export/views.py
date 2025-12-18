import os

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, mixins, status, permissions
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.views import APIView

from project.authorization.access import can_access_project
from project.models import PublishedProject, ProjectType
from export.serializers import (
    PublishedProjectSerializer,
    PublishedProjectDetailSerializer,
    ProjectVersionsSerializer
)
from search.views import get_content


class StandardRateThrottle(UserRateThrottle):
    """Rate limit for authenticated users"""
    rate = '100/hour'


class StandardAnonRateThrottle(AnonRateThrottle):
    """Rate limit for anonymous users"""
    rate = '20/hour'


class PublishedProjectList(mixins.ListModelMixin, generics.GenericAPIView):
    """
    List all published projects.

    Returns a paginated list of all published projects, ordered by ID.
    Supports filtering by resource type and search terms.

    Response includes:
        - Basic metadata (title, version, slug, DOIs, etc.)
        - License and DUA information
        - Storage sizes
        - Resource type (Database, Software, Challenge, Model) - as string
        - Access policy (Open, Restricted, Credentialed, Contributor Review) - as string
        - Topics (list of descriptive keywords)
        - Source URL (full URL to project page)

    Authentication:
        - Session or Basic authentication required
        - Rate limited: 100 requests/hour for authenticated users
        - Rate limited: 20 requests/hour for anonymous users
    """
    queryset = PublishedProject.objects.all().order_by('id')
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
        - Complete project metadata (title, version, slug, abstract, etc.)
        - License information
        - Project home page
        - DOI
        - Storage sizes
        - Resource type (Database, Software, Challenge, Model) - as string
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
        serializer = PublishedProjectDetailSerializer(project)
        return Response(serializer.data)


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


class ProjectSHA256Sums(APIView):
    """
    Download SHA256SUMS.txt file for a project.
    """
    permission_classes = [permissions.IsAuthenticated]

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
