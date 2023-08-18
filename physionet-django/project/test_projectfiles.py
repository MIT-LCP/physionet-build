from unittest import TestCase

from django.test import override_settings
from physionet.settings.base import StorageTypes
from project.models import ActiveProject
from project.projectfiles.gcs import GCSProjectFiles
from project.projectfiles.local import LocalProjectFiles


class TestProjectFiles(TestCase):
    @override_settings(STORAGE_TYPE=StorageTypes.LOCAL)
    def test_project_files_if_local_storage_type(self):
        project = ActiveProject()
        self.assertIsInstance(project.files, LocalProjectFiles)

    @override_settings(STORAGE_TYPE=StorageTypes.GCP)
    def test_project_files_if_google_cloud_storage_type(self):
        project = ActiveProject()
        self.assertIsInstance(project.files, GCSProjectFiles)
