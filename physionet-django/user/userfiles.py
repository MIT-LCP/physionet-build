import abc
import os

from django.conf import settings
from django.shortcuts import redirect
from storages.backends.gcloud import GoogleCloudStorage

from physionet.settings.base import StorageTypes
from physionet.utility import serve_file


class BaseUserFiles(abc.ABC):
    @abc.abstractmethod
    def serve_photo(self, user):
        raise NotImplementedError

    @abc.abstractmethod
    def get_photo_path(self, user):
        raise NotImplementedError

    @abc.abstractmethod
    def remove_photo(self, path):
        raise NotImplementedError


class LocalUserFiles(BaseUserFiles):
    def serve_photo(self, user):
        return serve_file(user.profile.photo.path)

    def get_photo_path(self, user):
        return user.photo.path

    def remove_photo(self, path):
        os.remove(path)


class GCSUserFiles(BaseUserFiles):
    def serve_photo(self, user):
        return redirect(user.profile.photo.url)

    def get_photo_path(self, user):
        # the name of the file is its path in GCS
        return user.photo.name

    def remove_photo(self, path):
        gcs = GoogleCloudStorage(
            bucket_name=settings.GCP_STORAGE_BUCKET_NAME
        )
        gcs.bucket.blob(path).delete()


class UserFiles:
    def __new__(cls):
        if settings.STORAGE_TYPE == StorageTypes.LOCAL:
            return LocalUserFiles()
        elif settings.STORAGE_TYPE == StorageTypes.GCP:
            return GCSUserFiles()
