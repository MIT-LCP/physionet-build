from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.project_home, name='project_home'),
    url(r'^create/$', views.create_project, name='create_project'),

    # Individual project pages
    url(r'^(?P<project_slug>\d+)/$', views.project_overview_redirect,
        name='project_overview_redirect'),
    url(r'^(?P<project_slug>\d+)/overview/$', views.project_overview,
        name='project_overview'),

    url(r'^(?P<project_slug>\d+)/authors/$', views.project_authors,
        name='project_authors'),
    url(r'^(?P<project_slug>\d+)/authors/move/$', views.move_author,
        name='move_author'),
    url(r'^(?P<project_slug>\d+)/authors/edit-affiliation/$', views.edit_affiliation,
        name='edit_affiliation'),

    url(r'^(?P<project_slug>\d+)/metadata/$', views.project_metadata,
        name='project_metadata'),
    # Edit a metadata item and reload the formset section
    url(r'^(?P<project_slug>\d+)/metadata/edit-item/$',
        views.edit_metadata_item,
        name='edit_metadata_item'),

    url(r'^(?P<project_slug>\d+)/access/$', views.project_access,
        name='project_access'),

    url(r'^(?P<project_slug>\d+)/identifiers/$', views.project_slugentifiers,
        name='project_slugentifiers'),

    url(r'^(?P<project_slug>\d+)/files/$', views.project_files,
        name='project_files'),
    url(r'^(?P<project_slug>\d+)/files/(?P<file_name>.+)$', views.serve_project_file,
        name='serve_project_file'),
    url(r'^(?P<project_slug>\d+)/project-files-panel/$', views.project_files_panel,
        name='project_files_panel'),

     url(r'^(?P<project_slug>\d+)/proofread/$', views.project_proofread,
        name='project_proofread'),

    url(r'^(?P<project_slug>\d+)/preview/$', views.project_preview,
        name='project_preview'),
    url(r'^(?P<project_slug>\d+)/preview-files-panel/$', views.preview_files_panel,
        name='preview_files_panel'),

    url(r'^(?P<project_slug>\d+)/submittable/$', views.check_submittable,
        name='check_submittable'),
    url(r'^(?P<project_slug>\d+)/submission/$', views.project_submission,
        name='project_submission'),
    url(r'^(?P<project_slug>\d+)/submission/history/$', views.project_submission_history,
        name='project_submission_history'),
]
