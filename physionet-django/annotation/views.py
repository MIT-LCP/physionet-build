from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
import json

from annotation.models import Annotation, AnnotationCollection, AnnotationType
from project.modelcomponents.publishedproject import PublishedProject
from .serializers import AnnotationSerializer, AnnotationCollectionSerializer, AnnotationTypeSerializer
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope
from oauth2_provider.decorators import protected_resource
from oauth2_provider.views.generic import ProtectedResourceView

class AnnotationCollectionCreateAPIView(ProtectedResourceView):
    """
    POST: Create an AnnotationCollection
    """
    def post(self, request, *args, **kwargs):
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST.dict()
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.POST.dict()
        
        serializer = AnnotationCollectionSerializer(data=data, context={'request': request})
        
        if serializer.is_valid():
            annotation_collection = serializer.save()
            return JsonResponse(serializer.data, status=201)
        else:
            return JsonResponse(serializer.errors, status=400)


class AnnotationTypeCreateAPIView(ProtectedResourceView):
    """
    POST: Create an AnnotationType
    """
    def post(self, request, *args, **kwargs):
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST.dict()
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.POST.dict()
        
        serializer = AnnotationTypeSerializer(data=data, context={'request': request})
        
        if serializer.is_valid():
            annotation_type = serializer.save()
            return JsonResponse(serializer.data, status=201)
        else:
            return JsonResponse(serializer.errors, status=400)


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