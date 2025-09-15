from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from annotation.models import Annotation, AnnotationCollection
from project.modelcomponents.publishedproject import PublishedProject
from .serializers import AnnotationSerializer, AnnotationCollectionSerializer
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope



class AnnotationCollectionCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an AnnotationCollection, return back the create AnnotationCollection ID
    """
    # permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    queryset = AnnotationCollection.objects.all()
    serializer_class = AnnotationCollectionSerializer