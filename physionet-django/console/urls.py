from django.urls import path

from console import views

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

    path('credential-applications/', views.credential_applications,
        name='credential_applications'),
    path('complete-credential-applications/', views.complete_credential_applications,
        name='complete_credential_applications'),
    path('complete-list-credentialed-people/', views.complete_list_credentialed_people,
        name='complete_list_credentialed_people'),
    path('past-credential-applications/<status>', views.past_credential_applications,
        name='past_credential_applications'),

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
    path('users/merge', views.merge_users, name='merge_users'),

    path('user-autocomplete/', views.UserAutocomplete.as_view(),
        name='user-autocomplete'),

    path('news/', views.news_console, name='news_console'),
    path('news/add/', views.news_add, name='news_add'),
    path('news/search/', views.news_search, name='news_search'),
    path('news/edit/<news_id>/', views.news_edit, name='news_edit'),

    path('featured/', views.featured_content, name='featured_content'),
    path('featured/add', views.add_featured, name='add_featured'),

    # guidelines
    path('guidelines/review/', views.guidelines_review, name='guidelines_review'),
]
