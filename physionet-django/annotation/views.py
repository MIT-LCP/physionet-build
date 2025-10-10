from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import json

from annotation.models import Annotation, AnnotationCollection, AnnotationType
from project.modelcomponents.publishedproject import PublishedProject
from .serializers import (
    AnnotationSerializer,
    AnnotationCollectionSerializer,
    AnnotationTypeSerializer,
)
from oauth2_provider.contrib.rest_framework import (
    TokenHasReadWriteScope,
    TokenHasScope,
    OAuth2Authentication,
)
from annotation.permissions import (
    AnnotationsScope,
    AnnotationsTypesScope,
    AnnotationsCollectionsScope,
)


class AnnotationCollectionCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an AnnotationCollection
    """

    authentication_classes = [OAuth2Authentication]
    permission_classes = [AnnotationsCollectionsScope, IsAuthenticated]
    serializer_class = AnnotationCollectionSerializer
    queryset = AnnotationCollection.objects.all()

class AnnotationCollectionReadAPIView(generics.RetrieveAPIView):
    authentication_classes = [OAuth2Authentication]
    permission_classes = [AnnotationsCollectionsScope, IsAuthenticated]
    serializer_class = AnnotationCollectionSerializer
    queryset = AnnotationCollection.objects.all()
    lookup_field = "slug"

    def get_queryset(self):
        return AnnotationCollection.objects.prefetch_related(
            'annotations',  # Current related_name (or 'annotations' if you change it)
            'annotations__annotation_type',  # Also prefetch annotation types
            'annotations__location',  # And locations
            'annotations__project'  # And projects
        )

class AnnotationTypeCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an AnnotationType
    """

    authentication_classes = [OAuth2Authentication]
    permission_classes = [AnnotationsTypesScope, IsAuthenticated]
    serializer_class = AnnotationTypeSerializer
    queryset = AnnotationType.objects.all()


class AnnotationCreateAPIView(generics.CreateAPIView):
    """
    POST: Create an Annotation, return back the create Annotation ID
    """

    authentication_classes = [OAuth2Authentication]
    permission_classes = [AnnotationsScope, IsAuthenticated]
    serializer_class = AnnotationSerializer
    queryset = Annotation.objects.all()

    def create(self, request, *args, **kwargs):
        collection = kwargs.get("collection_slug")
        if not collection:
            return Response(
                {"collection": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = request.data.copy()
        data["collection"] = collection

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )
