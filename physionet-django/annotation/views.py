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

from oauth2_provider.contrib.rest_framework import TokenHasScope
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

    # def post(self, request, *args, **kwargs):
    #     try:
    #         if request.content_type == 'application/json':
    #             data = json.loads(request.body)
    #         else:
    #             data = request.POST.dict()
    #     except (json.JSONDecodeError, UnicodeDecodeError):
    #         data = request.POST.dict()
        
    #     serializer = AnnotationTypeSerializer(data=data, context={'request': request})
        
    #     if serializer.is_valid():
    #         annotation_type = serializer.save()
    #         return JsonResponse(serializer.data, status=201)
    #     else:
    #         return JsonResponse(serializer.errors, status=400)


class AnnotationCreateAPIView(ProtectedResourceView):
    """
    POST: Create an Annotation
    """
    def post(self, request, *args, **kwargs):
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST.dict()
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.POST.dict()

        collection = kwargs.get('collection_slug')
        if not collection:
            return Response(
                {'collection_slug': ['This field is required.']}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        data['collection'] = collection

        serializer = AnnotationSerializer(data=data, context={'request': request})
        if serializer.is_valid(raise_exception=True):
            annotation = serializer.save()
            return JsonResponse(serializer.data, status=201)
        else:
            return JsonResponse(serializer.errors, status=400)