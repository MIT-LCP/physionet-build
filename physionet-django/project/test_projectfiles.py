import os
import tempfile
from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from django.test import override_settings
from physionet.settings.base import StorageTypes
from project.models import ActiveProject
from project.projectfiles.gcs import GCSProjectFiles
from project.projectfiles.local import LocalProjectFiles


class TestProjectFiles(TestCase):
    def test_restricted_file_extensions_uses_a_bounded_manifest(self):
        project = ActiveProject(slug='test-project')
        calls = []

        def manifest(path, max_files):
            calls.append((path, max_files))
            return [
                {'path': 'data/records.PKL.GZ'},
                {'path': 'notes/readme.txt'},
                {'path': 'model.JOBLIB'},
            ]

        project.__dict__['files'] = SimpleNamespace(
            file_root='projects',
            submission_file_manifest=manifest,
        )

        self.assertEqual(
            project.restricted_file_extensions(),
            ['.joblib', '.pkl.gz'],
        )
        self.assertEqual(
            calls,
            [('projects/active-projects/test-project', 1000)],
        )

    def test_local_submission_manifest_is_capped_before_scanning_all_files(self):
        files = LocalProjectFiles()
        with tempfile.TemporaryDirectory() as directory:
            for name in ('a.txt', 'b.txt', 'c.txt', 'd.txt'):
                with open(os.path.join(directory, name), 'w') as file:
                    file.write(name)

            with patch('project.projectfiles.local.os.stat', wraps=os.stat) as stat:
                manifest = files.submission_file_manifest(directory, max_files=2)

        self.assertEqual([entry['path'] for entry in manifest], ['a.txt', 'b.txt', 'c.txt'])
        self.assertEqual(stat.call_count, 3)

    def test_gcs_submission_manifest_ignores_directory_markers_at_the_cap(self):
        blobs = iter([
            SimpleNamespace(name='project/', size=0, updated=datetime.now()),
            SimpleNamespace(name='project/a.txt', size=1, updated=datetime.now()),
            SimpleNamespace(name='project/b.txt', size=2, updated=datetime.now()),
            SimpleNamespace(name='project/c.txt', size=3, updated=datetime.now()),
        ])
        files = GCSProjectFiles()

        with patch('project.projectfiles.gcs.GCSObject') as gcs_object:
            gcs_object.return_value.ls.return_value = blobs
            manifest = files.submission_file_manifest('bucket/project', max_files=2)

        self.assertEqual(
            [entry['path'] for entry in manifest], ['a.txt', 'b.txt', 'c.txt'])
        gcs_object.return_value.ls.assert_called_once_with()

    @override_settings(STORAGE_TYPE=StorageTypes.LOCAL)
    def test_project_files_if_local_storage_type(self):
        project = ActiveProject()
        self.assertIsInstance(project.files, LocalProjectFiles)

    @override_settings(STORAGE_TYPE=StorageTypes.GCP)
    def test_project_files_if_google_cloud_storage_type(self):
        project = ActiveProject()
        self.assertIsInstance(project.files, GCSProjectFiles)
