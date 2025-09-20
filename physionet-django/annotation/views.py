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
    POST: Create an AnnotationCollection, return back the create AnnotationCollection ID
    """
    
    def post(self, request, *args, **kwargs):
        try:
            # Try to parse JSON data first
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                # Use POST data for form submissions
                data = request.POST.dict()
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.POST.dict()
        
        serializer = AnnotationCollectionSerializer(data=data, context={'request': request})
        
        if serializer.is_valid():
            annotation_collection = serializer.save()
            return JsonResponse(serializer.data, status=201)
        else:
            return JsonResponse(serializer.errors, status=400)


class AnnotationTypeCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an AnnotationCollection, return back the create AnnotationCollection ID
    """
    # permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    queryset = AnnotationType.objects.all()
    serializer_class = AnnotationTypeSerializer

class AnnotationCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an Annotation, return back the create Annotation ID
    """
    queryset = Annotation.objects.all()
    serializer_class = AnnotationSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['collection'] = self.kwargs.get('collection')
        return context
    
    def create(self, request, *args, **kwargs):
        # Get collection_slug from URL
        collection = kwargs.get('collection')
        if not collection:
            return Response(
                {'collection': ['This field is required.']}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        # Add collection to request data
        data = request.data.copy()
        data['collection'] = collection
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)