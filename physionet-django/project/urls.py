from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.project_home, name='project_home'),
    url(r'^create/$', views.create_project, name='create_project'),

    # Individual project pages
    url(r'^(?P<project_slug>\w+)/$', views.project_overview_redirect,
        name='project_overview_redirect'),
    url(r'^(?P<project_slug>\w+)/overview/$', views.project_overview,
        name='project_overview'),
    url(r'^delete-project-success/$', views.delete_project_success, name='delete_project_success'),

    url(r'^(?P<project_slug>\w+)/authors/$', views.project_authors,
        name='project_authors'),
    url(r'^(?P<project_slug>\w+)/authors/move/$', views.move_author,
        name='move_author'),
    url(r'^(?P<project_slug>\w+)/authors/edit-affiliation/$', views.edit_affiliation,
        name='edit_affiliation'),

    url(r'^(?P<project_slug>\w+)/metadata/$', views.project_metadata,
        name='project_metadata'),
    # Edit a metadata item and reload the formset section
    url(r'^(?P<project_slug>\w+)/metadata/edit-item/$',
        views.edit_metadata_item,
        name='edit_metadata_item'),

    url(r'^(?P<project_slug>\w+)/access/$', views.project_access,
        name='project_access'),
    url(r'^(?P<project_slug>\w+)/access/load-license/$', views.load_license,
        name='load_license'),

    url(r'^(?P<project_slug>\w+)/identifiers/$', views.project_identifiers,
        name='project_identifiers'),

    url(r'^(?P<project_slug>\w+)/files/$', views.project_files,
        name='project_files'),
    url(r'^(?P<project_slug>\w+)/files/(?P<file_name>.+)$', views.serve_project_file,
        name='serve_project_file'),
    url(r'^(?P<project_slug>\w+)/project-files-panel/$', views.project_files_panel,
        name='project_files_panel'),

     url(r'^(?P<project_slug>\w+)/proofread/$', views.project_proofread,
        name='project_proofread'),

    url(r'^(?P<project_slug>\w+)/preview/$', views.project_preview,
        name='project_preview'),
    url(r'^(?P<project_slug>\w+)/preview-files-panel/$', views.preview_files_panel,
        name='preview_files_panel'),
    url(r'^(?P<project_slug>\w+)/view-license/$', views.project_license_preview,
        name='project_license_preview'),

    url(r'^(?P<project_slug>\w+)/integrity/$', views.check_integrity,
        name='check_integrity'),
    url(r'^(?P<project_slug>\w+)/submission/$', views.project_submission,
        name='project_submission'),

    url(r'^rejected/(?P<project_slug>\w+)/submission-history/$', views.rejected_submission_history,
        name='rejected_submission_history'),
    url(r'^published/(?P<project_slug>\w+)/submission-history/$', views.published_submission_history,
        name='published_submission_history'),
]
