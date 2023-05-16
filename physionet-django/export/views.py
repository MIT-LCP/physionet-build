from django.shortcuts import get_object_or_404

from project.models import PublishedProject

from export.serializers import PublishedProjectSerializer, PublishedProjectDetailSerializer, ProjectVersionsSerializer
from rest_framework import generics
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework import mixins
from rest_framework.response import Response

# Importing the get_content function from Search Module's views.py
from search.views import get_content

# Temporary imports for Database List Function.
from django.http import JsonResponse


def database_list(request):
    """
    List all published databases
    """
    projects = PublishedProject.objects.filter(resource_type=0).order_by(
        'publish_datetime')
    serializer = PublishedProjectSerializer(projects, many=True)
    return JsonResponse(serializer.data, safe=False)


class PublishedProjectList(mixins.ListModelMixin, generics.GenericAPIView):
    """
    List all Published Projects
    """
    queryset = PublishedProject.objects.all().order_by('id')
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = PublishedProjectSerializer

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class ProjectVersionList(mixins.ListModelMixin, generics.GenericAPIView):
    """
    List all versions of a specific project
    """

    serializer_class = ProjectVersionsSerializer

    def get_queryset(self):
        project_slug = self.kwargs.get('project_slug')
        queryset = PublishedProject.objects.filter(slug=project_slug).order_by('id')
        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class PublishedProjectDetail(mixins.RetrieveModelMixin, generics.GenericAPIView):
    """
    Retrieve an Published Project
    """

    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def get(self, request, project_slug, version, *args, **kwargs):
        project = get_object_or_404(PublishedProject, slug=project_slug, version=version)
        serializer = PublishedProjectDetailSerializer(project)
        return Response(serializer.data)


class PublishedProjectSearch(mixins.ListModelMixin, generics.GenericAPIView):
    """
    Search for a Published Project using the get_content function inside Search Module's views.py
    """

    # Getting the variables (resource_type, orderby, direction, search_term) from the API Call's Body.

    def get_queryset(self):
        resource_type = self.request.query_params.get('resource_type', 'types=0&types=1&types=2&types=3')
        orderby = self.request.query_params.get('orderby', 'relevance-desc')
        direction = self.request.query_params.get('direction', None)
        search_term = self.request.query_params.get('search_term', None)

        # Calling the get_content function inside Search Module's views.py
        queryset = get_content(resource_type, orderby, direction, search_term)

        return queryset
    
    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)
    