from django.urls import path, re_path
from graphene_django.views import GraphQLView
from export import views
from schema import schema

urlpatterns = [
    path('graphql', GraphQLView.as_view(graphiql=False, schema=schema),
         name='graphql'),
    path('rest/database-list/', views.database_list,
         name='database_list'),
    path('rest/software-list/', views.software_list,
         name='software_list'),
    path('rest/challenge-list/', views.challenge_list,
         name='challenge'),
    path('rest/model-list/', views.model_list,
         name='model'),
    path('rest/published-stats-list/', views.published_stats_list,
         name='published_stats_list'),
]
