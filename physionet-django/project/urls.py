from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.project_home, name='project_home'),
    url(r'^create/$', views.create_project, name='create_project'),
    
    url(r'^(?P<project_id>\d+)/$', views.project_overview, name='project_overview'),
    url(r'^(?P<project_id>\d+)/collaborators/$', views.project_collaborators, name='project_collaborators'),
    url(r'^(?P<project_id>\d+)/files/(?P<sub_item>.*)$', views.project_files, name='project_files'),
    url(r'^(?P<project_id>\d+)/metadata/$', views.project_metadata, name='project_metadata'),

    #url(r'^storage-allowance/(?P<project_id>\d+)/(?P<response>\s+)/', views.storage_allowance, name='storage_allowance')
]
