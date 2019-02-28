from django.urls import path, re_path

from . import views


urlpatterns = [
    path('rest/database-list/', views.database_list,
        name='database_list'),
    path('rest/software-list/', views.software_list,
        name='software_list'),

    path('rest/published-stats-list/', views.published_stats_list,
        name='published_stats_list'),
]
