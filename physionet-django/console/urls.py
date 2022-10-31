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
    path('project-access-manage/<pid>/', views.project_access_manage,
        name='project_access_manage'),
    path('published-projects/<project_slug>/<version>/',
        views.manage_published_project, name='manage_published_project'),
    path('data-access-request/<int:pk>/', views.access_request, name='access_request'),

    # Logs
    path('data-access-logs/', views.project_access_requests_list, name='project_access_requests_list'),
    path('data-access-logs/<int:pk>/', views.project_access_requests_detail, name='project_access_requests_detail'),
    path('project-access-logs/', views.project_access_logs, name='project_access_logs'),
    path('project-access-logs/<pid>/', views.project_access_logs_detail, name='project_access_logs_detail'),
    path('user-access-logs/', views.user_access_logs, name='user_access_logs'),
    path('user-access-logs/<pid>/', views.user_access_logs_detail, name='user_access_logs_detail'),
    path('download-project-accesses/<int:pk>/', views.download_project_accesses, name='download_project_accesses'),
    path('download-user-accesses/<int:pk>/', views.download_user_accesses, name='download_user_accesses'),
    path('gcp-signed-urls-logs/', views.gcp_signed_urls_logs, name='gcp_signed_urls_logs'),
    path('gcp-signed-urls-logs/<int:pk>/', views.gcp_signed_urls_logs_detail, name='gcp_signed_urls_logs_detail'),
    path('download-signed-urls-logs/<int:pk>/', views.download_signed_urls_logs, name='download_signed_urls_logs'),

    # Individual edit pages
    path('submitted-projects/<project_slug>/', views.submission_info_redirect, name='submission_info_redirect'),
    path('submitted-projects/<project_slug>/info/', views.submission_info, name='submission_info'),
    path('submitted-projects/<project_slug>/edit/', views.edit_submission, name='edit_submission'),
    path('submitted-projects/<project_slug>/copyedit/', views.copyedit_submission, name='copyedit_submission'),
    path('submitted-projects/<project_slug>/awaiting-authors/', views.awaiting_authors, name='awaiting_authors'),
    path('submitted-projects/<project_slug>/publish/', views.publish_submission, name='publish_submission'),
    path('publish-slug-available/<project_slug>/', views.publish_slug_available, name='publish_slug_available'),

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

    path('training/<status>/', views.training_list, name='training_list'),
    path('training/view/<int:pk>/', views.training_detail, name='training_detail'),
    path('training/process/<int:pk>/', views.training_process, name='training_process'),
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

    path('user-autocomplete/', views.UserAutocomplete.as_view(), name='user-autocomplete'),
    path('project-autocomplete/', views.ProjectAutocomplete.as_view(), name='project-autocomplete'),

    # editorial stats
    path('usage/editorial/stats/', views.editorial_stats, name='editorial_stats'),
    path('usage/credentialing/stats/', views.credentialing_stats, name='credentialing_stats'),
    path('usage/submission/stats/', views.submission_stats, name='submission_stats'),
    # static pages
    path('static-page/add/', views.static_page_add, name='static_page_add'),
    path('static-page/<int:page_pk>/edit/', views.static_page_edit, name='static_page_edit'),
    path('static-page/<int:page_pk>/delete/', views.static_page_delete, name='static_page_delete'),
    path('static-pages/', views.static_pages, name='static_pages'),
    path('static-pages/<int:page_pk>/', views.static_page_sections, name='static_page_sections'),
    path(
        'static-pages/<int:page_pk>/<int:section_pk>/delete/',
        views.static_page_sections_delete,
        name='static_page_sections_delete',
    ),
    path(
        'static-pages/<int:page_pk>/<int:section_pk>/edit/',
        views.static_page_sections_edit,
        name='static_page_sections_edit',
    ),
    path('licenses/', views.license_list, name='license_list'),
    path('licenses/<int:pk>/', views.license_detail, name='license_detail'),
    path('licenses/<int:pk>/delete/', views.license_delete, name='license_delete'),
    path('licenses/<int:pk>/new-version/', views.license_new_version, name='license_new_version'),
    path('duas/', views.dua_list, name='dua_list'),
    path('duas/<int:pk>/', views.dua_detail, name='dua_detail'),
    path('duas/<int:pk>/delete/', views.dua_delete, name='dua_delete'),
    path('duas/<int:pk>/new-version/', views.dua_new_version, name='dua_new_version'),
    path('code-of-conducts/', views.code_of_conduct_list, name='code_of_conduct_list'),
    path('code-of-conducts/<int:pk>/', views.code_of_conduct_detail, name='code_of_conduct_detail'),
    path('code-of-conducts/<int:pk>/delete/', views.code_of_conduct_delete, name='code_of_conduct_delete'),
    path(
        'code-of-conducts/<int:pk>/new-version/',
        views.code_of_conduct_new_version,
        name='code_of_conduct_new_version',
    ),
    path('code-of-conducts/<int:pk>/activate/', views.code_of_conduct_activate, name='code_of_conduct_activate'),
    # Lists of event components
    path('event/', views.event,
         name='event')
]
