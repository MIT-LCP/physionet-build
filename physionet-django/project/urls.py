from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.project_home, name='project_home'),
    url(r'^invitations/$', views.project_invitations, name='project_invitations'),


    url(r'^create/$', views.create_project, name='create_project'),


    url(r'^storage-requests/$', views.storage_requests,
        name='storage_requests'),

    url(r'^(?P<project_id>\d+)/overview/$', views.project_overview,
        name='project_overview'),
    url(r'^(?P<project_id>\d+)/authors/$', views.project_authors,
        name='project_authors'),
    url(r'^(?P<project_id>\d+)/collaborators/$', views.project_collaborators,
        name='project_collaborators'),
    url(r'^(?P<project_id>\d+)/files/(?P<sub_item>.*)$', views.project_files,
        name='project_files'),
    url(r'^(?P<project_id>\d+)/metadata/$', views.project_metadata,
        name='project_metadata'),
    url(r'^(?P<project_id>\d+)/submission/$', views.project_submission,
        name='project_submission'),
]
