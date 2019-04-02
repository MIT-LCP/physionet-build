from django.urls import path, re_path

from . import views
import project.views as project_views


urlpatterns = [
    path('search/topics/', views.topic_search, name='topic_search'),
    path('search/all-topics/', views.all_topics, name='all_topics'),

    # published project index pages
    path('data/', views.database_index, name='database_index'),
    path('software/', views.software_index, name='software_index'),
    path('challenge/', views.challenge_index, name='challenge_index'),
    path('content/', views.content_index, name='content_index'),

    # published project content
    path('content/<project_slug>/', project_views.published_project_latest,
        name='published_project_latest'),
    path('content/<project_slug>/<version>/', project_views.published_project,
        name='published_project'),
    path('content/<project_slug>/<version>/files-panel/',
        project_views.published_files_panel, name='published_files_panel'),
    # For protected access projects
    re_path('content/(?P<project_slug>\w+)/(?P<version>[\d\.]+)/get-file/(?P<full_file_name>.+)',
        project_views.serve_published_project_file,
        name='serve_published_project_file'),
    path('content/<project_slug>/<version>/get-zip/',
        project_views.serve_published_project_zip,
        name='serve_published_project_zip'),
    path('content/<project_slug>/<version>/view-license/',
        project_views.published_project_license,
        name='published_project_license'),
    path('sign-dua/<project_slug>/<version>/', project_views.sign_dua,
        name='sign_dua'),

    path('charts/', views.charts, name='charts'),
]
