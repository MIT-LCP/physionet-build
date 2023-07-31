from django.urls import path, re_path
from project import views

urlpatterns = [
    path('', views.project_home, name='project_home'),
    path('create/', views.create_project, name='create_project'),
    path(
        'delete-project-success/',
        views.delete_project_success,
        name='delete_project_success',
    ),
    path(
        'new-version/<project_slug>/',
        views.new_project_version,
        name='new_project_version',
    ),
    path(
        'archived/<project_slug>/submission-history/',
        views.archived_submission_history,
        name='archived_submission_history',
    ),
    path('published/<project_slug>/', views.published_versions, name='published_versions'),
    path(
        'published/<project_slug>/<version>/submission-history/',
        views.published_submission_history,
        name='published_submission_history',
    ),
    path(
        'project-autocomplete/',
        views.ProjectAutocomplete.as_view(),
        name='project-autocomplete',
    ),
    # Individual project pages
    path(
        '<project_slug>/',
        views.project_overview_redirect,
        name='project_overview_redirect',
    ),
    path('<project_slug>/overview/', views.project_overview, name='project_overview'),
    path('<project_slug>/authors/', views.project_authors, name='project_authors'),
    path('<project_slug>/authors/move/', views.move_author, name='move_author'),
    path(
        '<project_slug>/authors/edit-affiliation/',
        views.edit_affiliation,
        name='edit_affiliation',
    ),
    path('<project_slug>/content/', views.project_content, name='project_content'),
    # Edit a metadata item and reload the formset section
    path('<project_slug>/content/edit-item/', views.edit_content_item, name='edit_content_item'),
    path('<project_slug>/access/', views.project_access, name='project_access'),
    path('<project_slug>/discovery/', views.project_discovery, name='project_discovery'),
    path('<project_slug>/files/', views.project_files, name='project_files'),
    path('<project_slug>/files/<path:subdir>/', views.project_files, name='project_files'),
    re_path(
        r'^(?P<project_slug>\w+)/files/(?P<file_name>.+)$',
        views.serve_active_project_file,
        name='serve_active_project_file',
    ),
    path('<project_slug>/project-files-panel/', views.project_files_panel, name='project_files_panel'),
    path('<project_slug>/proofread/', views.project_proofread, name='project_proofread'),
    path('<project_slug>/preview/', views.project_preview, name='project_preview'),
    path('<project_slug>/preview/<path:subdir>/', views.project_preview, name='project_preview_subdir'),
    path(
        '<project_slug>/preview/<path:file_name>',
        views.display_active_project_file,
        name='display_active_project_file',
    ),
    path('<project_slug>/preview-files-panel/', views.preview_files_panel, name='preview_files_panel'),
    path('<project_slug>/view-license/', views.project_license_preview, name='project_license_preview'),
    path('<project_slug>/view-dua/', views.project_dua_preview, name='project_dua_preview'),
    path('<project_slug>/integrity/', views.check_integrity, name='check_integrity'),
    path('<project_slug>/submission/', views.project_submission, name='project_submission'),
    path('<project_slug>/ethics/', views.project_ethics, name='project_ethics'),
    path('<project_slug>/ethics/edit-document/', views.edit_ethics, name='edit_ethics'),
    path('ethics/<path:file_name>/', views.serve_document, name='serve_document'),
    path(
        '<project_slug>/view-required-trainings/',
        views.project_required_trainings_preview,
        name='project_required_trainings_preview',
    ),
    path(
        '<project_slug>/<version>/request_access/<int:access_type>',
        views.published_project_request_access,
        name='published_project_request_access',
    ),
    re_path(
        r'^(?P<project_slug>\w+)/download/(?P<full_file_name>.*)$',
        views.serve_active_project_file_editor,
        name='serve_active_project_file_editor',
    ),
    path(
        '<project_slug>/generate-signed-url/',
        views.generate_signed_url,
        name='generate_signed_url',
    ),
]

TEST_CASES = {
    'project_files': {
        '_user_': 'rgmark',
        'project_slug': 'T108xFtYkRAxiRiuOLEJ',
        'subdir': 'notes',
    }
}
