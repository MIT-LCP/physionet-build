import warnings

from django.conf import settings
from physionet.settings.base import StorageTypes
from project.projectfiles.gcs import GCSProjectFiles
from project.projectfiles.local import LocalProjectFiles


class ProjectFiles:
    def __new__(cls):
        warnings.warn("use project.files instead of ProjectFiles()",
                      DeprecationWarning, stacklevel=2)
        if settings.STORAGE_TYPE == StorageTypes.LOCAL:
            return LocalProjectFiles()
        elif settings.STORAGE_TYPE == StorageTypes.GCP:
            return GCSProjectFiles()
