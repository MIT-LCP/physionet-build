from django.shortcuts import get_object_or_404

from project.models import PublishedProject

from export.serializers import PublishedProjectSerializer, PublishedProjectDetailSerializer
from rest_framework import generics
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework import mixins
from rest_framework.response import Response


class PublishedProjectList(mixins.ListModelMixin, generics.GenericAPIView):
    """
    List all Published Projects
    """
    queryset = PublishedProject.objects.all().order_by('id')
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    serializer_class = PublishedProjectSerializer

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class PublishedProjectDetail(mixins.RetrieveModelMixin, generics.GenericAPIView):
    """
    Retrieve an Published Project
    """

    authentication_classes = [SessionAuthentication, BasicAuthentication]

    def get(self, request, slug, version, *args, **kwargs):
        project = get_object_or_404(PublishedProject, slug=slug, version=version)
        serializer = PublishedProjectDetailSerializer(project)
        return Response(serializer.data)
