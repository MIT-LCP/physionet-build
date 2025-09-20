from django.urls import path
from annotation.views import *

app_name = 'annotation'

# urlpatterns = [
#     path('projects/<slug:project_slug>/<slug:version>/collections/', 
#          views.ProjectAnnotationCollections.as_view(), 
#          name='project-annotation-collections'),
#     path('collections/<uuid:collection_id>/annotations/', 
#          views.AnnotationCreate.as_view(), 
#          name='collection-annotations'),
# ]

urlpatterns = [
    path('annotations/collection/create/', 
         AnnotationCollectionCreateAPIView.as_view(), 
         name='annotation-collection-create'),
    path('annotations/type/create/', 
         AnnotationTypeCreateAPIView.as_view(), 
         name='annotation-type-create'),
    path('annotations/collections/<slug:collection_slug>/', 
         AnnotationCreateAPIView.as_view(), 
         name='annotation-create-view')
]
