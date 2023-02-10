from django.shortcuts import get_object_or_404

from project.models import PublishedProject

from export.serializers import PublishedProjectSerializer, PublishedProjectDetailSerializer, ProjectVersionsSerializer
from rest_framework import generics
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework import mixins
from rest_framework.response import Response

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


class PublishedProjectLatestDetail(mixins.RetrieveModelMixin, generics.GenericAPIView):
    """
    Retrieve an Published Project
    """

    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def get(self, request, project_slug, *args, **kwargs):
        version = PublishedProject.objects.get(slug=project_slug,
                  is_latest_version=True).version
        project = get_object_or_404(PublishedProject, slug=project_slug, version=version)
        serializer = PublishedProjectDetailSerializer(project)
        return Response(serializer.data)


class PublishedProjectDetail(mixins.RetrieveModelMixin, generics.GenericAPIView):
    """
    Retrieve an Published Project
    """

    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def get(self, request, project_slug, version, *args, **kwargs):
        project = get_object_or_404(PublishedProject, slug=project_slug, version=version)
        serializer = PublishedProjectDetailSerializer(project)
        return Response(serializer.data)
