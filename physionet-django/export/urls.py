from django.urls import path, re_path

from export import views


urlpatterns = [
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

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {}
