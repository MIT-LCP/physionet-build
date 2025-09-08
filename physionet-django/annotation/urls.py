from django.urls import path
from . import views

urlpatterns = [
    # 1) Getting all AnnotationCollections from specific project & version
    path(
        'v1/projects/<str:project_slug>/<str:version>/annotations/',
        views.ProjectAnnotationCollectionsList.as_view(),
        name='project_annotation_collections_list',
    ),

    # 2) Posting Annotation to specific AnnotationCollection
    # 3) Getting all Annotations from specific AnnotationCollection
    path(
        'v1/annotations/collections/<int:collection_id>',
        views.CollectionAnnotationListCreate.as_view(),
        name='collection_annotation_list_create',
    ),
]