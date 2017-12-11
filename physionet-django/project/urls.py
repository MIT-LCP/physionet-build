from django.conf.urls import url
from django.urls import reverse_lazy

from .views import (project_home, create_project, edit_project,
    project_collaborators, project_files, project_metadata)


urlpatterns = [
    url(r'^$', project_home, name='project_home'),
    url(r'^create/$', create_project, name='create_project'),

    url(r'^(?P<project>[0-9A-Za-z_\-]+)/$', edit_project, name='edit_project'),

    url(r'^(?P<project>[0-9A-Za-z_\-]+)/collaborators/$', project_collaborators, name='project_collaborators'),
    url(r'^(?P<project>[0-9A-Za-z_\-]+)/files/$', project_files, name='project_files'),
    url(r'^(?P<project>[0-9A-Za-z_\-]+)/metadata/$', project_metadata, name='project_metadata'),
]
