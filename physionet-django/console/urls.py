from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.console_home,
        name='console_home'),
    url(r'^editor-home/$', views.editor_home,
        name='editor_home'),
    # Lists of projects
    url(r'^unsubmitted-projects/$', views.unsubmitted_projects,
        name='unsubmitted_projects'),
    url(r'^submitted-projects/$', views.submitted_projects,
        name='submitted_projects'),
    url(r'^published-projects/$', views.published_projects,
        name='published_projects'),
    url(r'^rejected-submissions/$', views.rejected_submissions,
        name='rejected_submissions'),

    # Individual edit pages
    url(r'^submitted-projects/(?P<project_slug>\w+)/$',
        views.submission_info_redirect, name='submission_info_redirect'),
    url(r'^submitted-projects/(?P<project_slug>\w+)/info/$',
        views.submission_info, name='submission_info'),
    url(r'^submitted-projects/(?P<project_slug>\w+)/edit/$',
        views.edit_submission, name='edit_submission'),
    url(r'^submitted-projects/(?P<project_slug>\w+)/copyedit/$',
        views.copyedit_submission, name='copyedit_submission'),
    url(r'^submitted-projects/(?P<project_slug>\w+)/awaiting-authors/$',
        views.awaiting_authors, name='awaiting_authors'),
    url(r'^submitted-projects/(?P<project_slug>\w+)/publish/$',
        views.publish_submission, name='publish_submission'),

    url(r'^storage-requests/$', views.storage_requests,
        name='storage_requests'),
    url(r'^users/$', views.users, name='user_list'),

    url(r'^credential-applications/$', views.credential_applications,
        name='credential_applications'),
    url(r'^past-credential-applications/$', views.past_credential_applications,
        name='past_credential_applications'),
    url(r'^credentialed-users/$', views.credentialed_users,
        name='credentialed_users'),
    url(r'^credentialed-users/(?P<username>[\w\-\.]+)/$',
        views.credentialed_user_info, name='credentialed_user_info')
    url(r'^credential-applications/(?P<application_slug>\w+)/view/$',
        views.view_credential_application,
        name='view_credential_application'),
    url(r'^credential-applications/(?P<application_slug>\w+)/process/$',
        views.process_credential_application,
        name='process_credential_application'),

]
