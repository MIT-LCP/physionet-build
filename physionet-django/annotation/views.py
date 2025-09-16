from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from annotation.models import Annotation, AnnotationCollection, AnnotationType
from project.modelcomponents.publishedproject import PublishedProject
from .serializers import AnnotationSerializer, AnnotationCollectionSerializer, AnnotationTypeSerializer
from oauth2_provider.contrib.rest_framework import TokenHasReadWriteScope, TokenHasScope



class AnnotationCollectionCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an AnnotationCollection, return back the create AnnotationCollection ID
    """
    # permission_classes = [permissions.IsAuthenticated, TokenHasReadWriteScope]
    queryset = AnnotationCollection.objects.all()
    serializer_class = AnnotationCollectionSerializer

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