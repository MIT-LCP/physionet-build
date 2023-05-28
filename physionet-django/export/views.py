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
        breakpoint()
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


from rest_framework import generics, mixins
from search.views import get_content

class PublishedProjectSearch(mixins.ListModelMixin, generics.GenericAPIView):
    """
    Search for a Published Project using the get_content function inside Search Module's views.py
    """

    serializer_class = PublishedProjectSerializer

    def get_queryset(self):
        resource_type = self.request.GET.get('resource_type', '0,1,2,3')
        resource_type = [int(x) for x in resource_type.split(',')]
        orderby = self.request.GET.get('orderby', 'relevance-desc')
        search_term = self.request.GET.get('search_term', ' ')

        # Ensure that resource_type is a list of integers
        if not all(isinstance(x, int) for x in resource_type):
            resource_type = [int(x) for x in resource_type if str(x).isdigit()]

        # Handle orderby parameter
        if orderby == 'relevance-desc':
            queryset = get_content(resource_type, 'relevance', 'desc', search_term)
        elif orderby == 'publish_datetime-desc':
            queryset = PublishedProject.objects.filter(resource_type__in=resource_type).order_by('-publish_datetime')
        elif orderby == 'publish_datetime-asc':
            queryset = PublishedProject.objects.filter(resource_type__in=resource_type).order_by('publish_datetime')
        else:
            # Default to relevance descending order
            queryset = get_content(resource_type, 'relevance', 'desc', search_term)

        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)
    