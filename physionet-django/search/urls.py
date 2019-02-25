from django.urls import path

from . import views


urlpatterns = [
    path('search/google-custom-search/', views.google_custom_search,
        name='google_custom_search'),
    path('search/redirect-google-custom-search/',
        views.redirect_google_custom_search,
        name='redirect_google_custom_search'),

    path('search/topics/', views.topic_search, name='topic_search'),
    path('search/all-topics/', views.all_topics, name='all_topics'),

    # published project index pages
    path('data/', views.database_index, name='database_index'),
    path('software/', views.software_index, name='software_index'),
    path('content/', views.content_index, name='content_index'),

    path('data/stats/', views.database_stats, name='database_stats'),
]
