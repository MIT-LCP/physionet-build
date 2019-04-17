from django.urls import path

from . import views

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
    path('past-credential-applications/', views.past_credential_applications,
        name='past_credential_applications'),

    path('credentialed-users/<username>/',
        views.credentialed_user_info, name='credentialed_user_info'),
    path('view-credential-applications/<application_slug>/',
        views.view_credential_application,
        name='view_credential_application'),
    path('credential-applications/<application_slug>/process/',
        views.process_credential_application,
        name='process_credential_application'),


    path('users/all/', views.users, name='user_list'),
    path('users/admin/', views.admin_users, name='user_list_admin'),
    path('users/inactive/', views.inactive_users, name='user_list_inactive'),
    # path('users/lcp/', views.lcp_affiliates, name='lcp_affiliates'),

    path('news/', views.console_news, name='console_news'),
    path('news/edit/<news_id>/', views.edit_news, name='edit_news'),
    path('news/add/', views.add_news, name='add_news'),

    # guidelines
    path('guidelines/review/', views.guidelines_review, name='guidelines_review'),
]
