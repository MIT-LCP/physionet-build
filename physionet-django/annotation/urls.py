from django.urls import path
from annotation.views import (
    AnnotationCollectionCreateAPIView,
    AnnotationCollectionReadAPIView,
    AnnotationTypeCreateAPIView,
    AnnotationCreateAPIView,
)

app_name = "annotation"

urlpatterns = [
    path(
        "annotations/collection/create/",
        AnnotationCollectionCreateAPIView.as_view(),
        name="annotation-collection-create",
    ),
    path(
        "annotations/collection/<slug:slug>/",
        AnnotationCollectionReadAPIView.as_view(),
        name="annotation-collection-read",
    ),
    path(
        "annotations/type/create/",
        AnnotationTypeCreateAPIView.as_view(),
        name="annotation-type-create",
    ),
    path(
        "annotations/collections/<slug:collection_slug>/",
        AnnotationCreateAPIView.as_view(),
        name="annotation-create-view",
    ),
]
