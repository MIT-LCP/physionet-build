from console import views
from django.urls import path

urlpatterns = [
    path('', views.console_home,
        name='console_home'),
    path('editor-home/', views.editor_home,
        name='editor_home'),
    # Lists of projects
    path('unsubmitted-projects/', views.unsubmitted_projects,
        name='unsubmitted_projects'),
    path('submitted-projects/', views.submitted_projects,
        name='submitted_projects'),
    path('published-projects/', views.published_projects,
        name='published_projects'),
    path('rejected-submissions/', views.rejected_submissions,
        name='rejected_submissions'),
    path('project-access', views.project_access,
        name='protected_project_access'),
    path('project-access-manage/<pid>/', views.project_access_manage,
        name='project_access_manage'),
    path('published-projects/<project_slug>/<version>/',
        views.manage_published_project, name='manage_published_project'),

    # Logs
    path('project-access-logs/', views.project_access_logs,
        name='project_access_logs'),
    path('project-access-logs/<pid>/', views.project_access_logs_detail,
        name='project_access_logs_detail'),
    path('user-access-logs/', views.user_access_logs,
        name='user_access_logs'),
    path('user-access-logs/<pid>/', views.user_access_logs_detail,
        name='user_access_logs_detail'),
    path('download-project-accesses/<int:pk>/', views.download_project_accesses,
        name='download_project_accesses'),
    path('download-user-accesses/<int:pk>/', views.download_user_accesses,
        name='download_user_accesses'),
    path('gcp-signed-urls-logs/', views.gcp_signed_urls_logs,
        name='gcp_signed_urls_logs'),

    # Individual edit pages
    path('submitted-projects/<project_slug>/',
        views.submission_info_redirect, name='submission_info_redirect'),
    path('submitted-projects/<project_slug>/info/',
        views.submission_info, name='submission_info'),
    path('submitted-projects/<project_slug>/edit/',
        views.edit_submission, name='edit_submission'),
    path('submitted-projects/<project_slug>/copyedit/',
        views.copyedit_submission, name='copyedit_submission'),
    path('submitted-projects/<project_slug>/awaiting-authors/',
        views.awaiting_authors, name='awaiting_authors'),
    path('submitted-projects/<project_slug>/publish/',
        views.publish_submission, name='publish_submission'),
    path('publish-slug-available/<project_slug>/',
        views.publish_slug_available, name='publish_slug_available'),

    path('storage-requests/', views.storage_requests,
        name='storage_requests'),

    path('complete-credential-applications/', views.complete_credential_applications,
         name='complete_credential_applications'),
    path('complete-list-credentialed-people/', views.complete_list_credentialed_people,
        name='complete_list_credentialed_people'),
    path('credential-applications/<status>', views.credential_applications,
        name='credential_applications'),
    path('known-references/', views.known_references,
        name='known_references'),
    path('known-references/search/', views.known_references_search,
        name='known_references_search'),
    path('credential_processing/', views.credential_processing,
        name='credential_processing'),

    path('credentialed-users/<username>/',
        views.credentialed_user_info, name='credentialed_user_info'),
    path('view-credential-applications/<application_slug>/',
        views.view_credential_application,
        name='view_credential_application'),
    path('credential-applications/<application_slug>/process/',
        views.process_credential_application,
        name='process_credential_application'),

    # Download a CSV of the people that have a credentialed DB access
    path('download_credentialed_users/',
        views.download_credentialed_users,
        name="download_credentialed_users"),

    path('users/search/<group>/', views.users_search, name='users_list_search'),
    path('users/<group>/', views.users, name='users'),
    path('user/manage/<username>/', views.user_management,
        name='user_management'),

    path('news/', views.news_console, name='news_console'),
    path('news/add/', views.news_add, name='news_add'),
    path('news/search/', views.news_search, name='news_search'),
    path('news/edit/<news_id>/', views.news_edit, name='news_edit'),

    path('featured/', views.featured_content, name='featured_content'),
    path('featured/add', views.add_featured, name='add_featured'),

    # guidelines
    path('guidelines/review/', views.guidelines_review, name='guidelines_review'),

    path('user-autocomplete/', views.UserAutocomplete.as_view(),
        name='user-autocomplete'),
    path('project-autocomplete/', views.ProjectAutocomplete.as_view(),
        name='project-autocomplete'),

    # editorial stats
    path('usage/editorial/stats/', views.editorial_stats, name='editorial_stats'),
    path('usage/credentialing/stats/', views.credentialing_stats,
         name='credentialing_stats'),
    path('usage/submission/stats/', views.submission_stats, name='submission_stats'),
    # static pages
    path('static-pages/', views.static_pages, name='static_pages'),
    path('static-pages/<str:page>/', views.static_page_sections, name='static_page_sections'),
    path(
        'static-pages/<str:page>/<int:pk>/delete/',
        views.static_page_sections_delete,
        name='static_page_sections_delete',
    ),
    path('static-pages/<str:page>/<int:pk>/edit/', views.static_page_sections_edit, name='static_page_sections_edit'),
]
