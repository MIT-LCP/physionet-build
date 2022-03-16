from django.urls import path, re_path

from search import views
import project.views as project_views


urlpatterns = [
    path('search/topics/', views.topic_search, name='topic_search'),
    path('search/all-topics/', views.all_topics, name='all_topics'),

    # published project index pages
    path('data/', views.database_index, name='database_index'),
    path('software/', views.software_index, name='software_index'),
    path('challenge/', views.challenge_index, name='challenge_index'),
    path('model/', views.model_index, name='model_index'),
    path('content/', views.content_index, name='content_index'),

    # published project content
    re_path('^(?P<anonymous_url>[\w\d]{64})/$', project_views.anonymous_login,
        name='anonymous_login'),
    path('content/<project_slug>/', project_views.published_project_latest,
        name='published_project_latest'),
    path('content/<project_slug>/<version>/', project_views.published_project,
        name='published_project'),
    re_path('^content/(?P<project_slug>[\w\-]+)/(?P<version>[\d\.]+)/(?P<subdir>.+)/$',
        project_views.published_project, name='published_project_subdir'),
    path('content/<project_slug>/files-panel/<version>/',
        project_views.published_files_panel, name='published_files_panel'),
    re_path('^files/(?P<project_slug>[\w-]+)/(?P<version>[\d\.]+)/(?P<full_file_name>.*)$',
        project_views.serve_published_project_file,
        name='serve_published_project_file'),
    re_path('^content/(?P<project_slug>[\w\-]+)/(?P<version>[\d\.]+)/(?P<full_file_name>.+)$',
        project_views.display_published_project_file,
        name='display_published_project_file'),
    path('content/<project_slug>/get-zip/<version>/',
        project_views.serve_published_project_zip,
        name='serve_published_project_zip'),
    path(
        'content/<project_slug>/view-license/<version>/',
        project_views.published_project_license,
        name='published_project_license',
    ),
    path(
        'content/<project_slug>/view-required-training/<version>/',
        project_views.published_project_required_training,
        name='published_project_required_training',
    ),
    path('sign-dua/<project_slug>/<version>/', project_views.sign_dua, name='sign_dua'),
    path('request-access/<project_slug>/<version>/', project_views.request_data_access, name='request_data_access'),
    path(
        'request-access-status/<project_slug>/<version>/',
        project_views.data_access_request_status,
        name='data_access_request_status',
    ),
    path(
        'access-requests/<project_slug>/<version>/<user_id>/',
        project_views.data_access_request_view,
        name='data_access_request_view',
    ),
    path(
        'access-requests/<project_slug>/<version>/',
        project_views.data_access_requests_overview,
        name='data_access_requests_overview',
    ),
    path(
        'manage-reviewers/<project_slug>/<version>/',
        project_views.manage_data_access_reviewers,
        name='manage_data_access_reviewers',
    ),
    path('charts/', views.charts, name='charts'),

    # Redirect from legacy
    path('physiobank/', views.physiobank),
    path('physiobank/database/', views.physiobank),
    path('physiotools/', views.physiotools),
    path('physiobank/database/wfdbcal', views.wfdbcal),
    re_path('^physiobank/database/(?P<project_slug>[\w\-]+)/$', views.redirect_project),
    re_path('^physiotools/(?P<project_slug>[\w\-]+)/$', views.redirect_project),
    re_path('^challenge/(?P<year>\w+)/$', views.redirect_challenge_project),
]
