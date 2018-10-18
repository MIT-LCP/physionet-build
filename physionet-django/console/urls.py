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
    # published projects

    # Individual edit pages
    url(r'^submitted-projects/(?P<project_slug>\w+)/edit/$',
        views.edit_submission, name='edit_submission'),
    url(r'^submitted-projects/(?P<project_slug>\w+)/copyedit/$',
        views.copyedit_submission, name='copyedit_submission'),
    url(r'^submitted-projects/(?P<project_slug>\w+)/publish/$',
        views.publish_submission, name='publish_submission'),

    url(r'^storage-requests/$', views.storage_requests,
        name='storage_requests'),
    url(r'^users/$', views.users, name='user_list'),

]
