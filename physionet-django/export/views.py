from django.shortcuts import get_object_or_404

from project.models import PublishedProject

from export.serializers import PublishedProjectSerializer, PublishedProjectDetailSerializer, ProjectVersionsSerializer
from rest_framework import generics
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework import mixins
from rest_framework.response import Response
from search.views import get_content
from project.models import ProjectType
from rest_framework.renderers import JSONRenderer

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
    serializer_class = PublishedProjectSerializer

    def check_resource_type(self, resource_type):
        """
        Check if the resource_type requested is valid. Returns True if valid, else False
        """
        available_resource_types = ProjectType.objects.all().values_list('name', flat=True)
        for r_type in resource_type:
            if r_type != 'all' and r_type.capitalize() not in available_resource_types:
                return False
        return True

    def get_queryset(self):
        """
        Modifying the get_queryset method to return the queryset based on the search_term and resource_type
        """
        resource_type = self.request.GET.getlist('resource_type', ['all'])
        search_term = self.request.GET.get('search_term', ' ')

        # If resource_type is 'all', then get all the resource types
        if 'all' in resource_type:
            resource_type_list = ProjectType.objects.all().values_list('name', flat=True)
        else:
            resource_type_list = resource_type
            resource_type_list = [x.capitalize() for x in resource_type_list]

        # convert the resource_type_list to the respective ids
        resource_type_list = ProjectType.objects.filter(name__in=resource_type_list).values_list('id', flat=True)

        # Default to relevance descending order
        queryset = get_content(resource_type_list, 'relevance', 'desc', search_term)

        return queryset

    def get(self, request, *args, **kwargs):
        """
        Default get method for PublishedProjectSearch that takes in the search_term
        and resource_type as query parameters
        """
        # check if the resource_type requested is valid
        resource_type = self.request.GET.getlist('resource_type', ['all'])
        if not self.check_resource_type(resource_type):
            return Response({'error': 'Invalid resource_type'}, status=400)

        return self.list(request, *args, **kwargs)
