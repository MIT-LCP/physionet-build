from django.urls import path, re_path

from . import views


urlpatterns = [
    path('', views.project_home, name='project_home'),
    path('create/', views.create_project, name='create_project'),
    path('delete-project-success/', views.delete_project_success,
        name='delete_project_success'),

    path('rejected/<project_slug>/submission-history/', views.rejected_submission_history,
        name='rejected_submission_history'),
    path('published/<project_slug>/submission-history/', views.published_submission_history,
        name='published_submission_history'),

    # Individual project pages
    path('<project_slug>/', views.project_overview_redirect,
        name='project_overview_redirect'),
    path('<project_slug>/overview/', views.project_overview,
        name='project_overview'),

    path('<project_slug>/authors/', views.project_authors,
        name='project_authors'),
    path('<project_slug>/authors/move/', views.move_author,
        name='move_author'),
    path('<project_slug>/authors/edit-affiliation/', views.edit_affiliation,
        name='edit_affiliation'),

    path('<project_slug>/metadata/', views.project_metadata,
        name='project_metadata'),
    # Edit a metadata item and reload the formset section
    path('<project_slug>/metadata/edit-item/',
        views.edit_metadata_item,
        name='edit_metadata_item'),

    path('<project_slug>/access/', views.project_access,
        name='project_access'),
    path('<project_slug>/access/load-license/', views.load_license,
        name='load_license'),

    path('<project_slug>/identifiers/', views.project_identifiers,
        name='project_identifiers'),

    path('<project_slug>/files/', views.project_files,
        name='project_files'),
    re_path('(?P<project_slug>\w+)/files/(?P<file_name>.+)', views.serve_project_file,
        name='serve_project_file'),
    path('<project_slug>/project-files-panel/', views.project_files_panel,
        name='project_files_panel'),

     path('<project_slug>/proofread/', views.project_proofread,
        name='project_proofread'),

    path('<project_slug>/preview/', views.project_preview,
        name='project_preview'),
    path('<project_slug>/preview-files-panel/', views.preview_files_panel,
        name='preview_files_panel'),
    path('<project_slug>/view-license/', views.project_license_preview,
        name='project_license_preview'),

    path('<project_slug>/integrity/', views.check_integrity,
        name='check_integrity'),
    path('<project_slug>/submission/', views.project_submission,
        name='project_submission'),

    path('sign-dua/<published_project_slug>/', views.sign_dua,
        name='sign_dua'),
]
