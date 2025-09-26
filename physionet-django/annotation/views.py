from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
import json

from annotation.models import Annotation, AnnotationCollection, AnnotationType
from project.modelcomponents.publishedproject import PublishedProject
from .serializers import AnnotationSerializer, AnnotationCollectionSerializer, AnnotationTypeSerializer
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope, OAuth2Authentication
from oauth2_provider.decorators import protected_resource
from oauth2_provider.views.generic import ProtectedResourceView

from rest_framework.permissions import SAFE_METHODS


class AnnotationsScope(TokenHasScope):
    def get_scopes(self, request, view):
        return ["annotations:view"] if request.method in SAFE_METHODS else ["annotations:edit"]


class AnnotationCollectionCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an AnnotationCollection
    """
    authentication_classes = [OAuth2Authentication]
    permission_classes = [AnnotationsScope, IsAuthenticated]
    serializer_class = AnnotationCollectionSerializer
    queryset = AnnotationCollection.objects.all()
    required_scopes = ['annotations:edit']


class AnnotationTypeCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an AnnotationType
    """
    authentication_classes = [OAuth2Authentication]
    permission_classes = [AnnotationsScope, IsAuthenticated]
    serializer_class = AnnotationTypeSerializer
    queryset = AnnotationType.objects.all()
    required_scopes = ['annotations:edit']


class AnnotationCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an Annotation, return back the create Annotation ID
    """
    authentication_classes = [OAuth2Authentication]
    permission_classes = [AnnotationsScope, IsAuthenticated]
    serializer_class = AnnotationSerializer
    queryset = Annotation.objects.all()
    required_scopes = ['annotations:edit']

    def create(self, request, *args, **kwargs):
        collection = kwargs.get('collection_slug')
        if not collection:
            return Response(
                {'collection': ['This field is required.']},
                status=status.HTTP_400_BAD_REQUEST
            )
        data = request.data.copy()
        data['collection'] = collection

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)