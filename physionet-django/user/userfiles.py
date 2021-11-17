import abc
import os

from django.conf import settings
from django.shortcuts import redirect
from physionet.gcs import GCSObject
from physionet.settings.base import StorageTypes
from physionet.utility import serve_file


class BaseUserFiles(abc.ABC):
    @abc.abstractproperty
    def file_root(self):
        raise NotImplementedError

    @abc.abstractmethod
    def serve_photo(self, user):
        raise NotImplementedError

    @abc.abstractmethod
    def get_photo_path(self, user):
        raise NotImplementedError

    @abc.abstractmethod
    def remove_photo(self, path):
        raise NotImplementedError

    @abc.abstractmethod
    def rename(self, source_path, user):
        raise NotImplementedError


class LocalUserFiles(BaseUserFiles):
    @property
    def file_root(self):
        return settings.MEDIA_ROOT

    def serve_photo(self, user):
        return serve_file(user.profile.photo.path)

    def get_photo_path(self, user):
        return user.photo.path

    def remove_photo(self, path):
        os.remove(path)

    def rename(self, source_path, user):
        if os.path.exists(source_path):
            os.rename(source_path, user.file_root())


class GCSUserFiles(BaseUserFiles):
    @property
    def file_root(self):
        return settings.GCP_STORAGE_BUCKET_NAME

    def serve_photo(self, user):
        return redirect(user.profile.photo.url)

    def get_photo_path(self, user):
        # the name of the file is its path in GCS
        return user.photo.name

    def remove_photo(self, path):
        target_path = os.path.join(settings.GCP_STORAGE_BUCKET_NAME, path)
        GCSObject(target_path).rm()

    def rename(self, source_path, user):
        target_path = os.path.join(settings.GCP_STORAGE_BUCKET_NAME, user.file_root(relative=True))
        GCSObject(source_path).rename(GCSObject(target_path))


class UserFiles:
    def __new__(cls):
        if settings.STORAGE_TYPE == StorageTypes.LOCAL:
            return LocalUserFiles()
        elif settings.STORAGE_TYPE == StorageTypes.GCP:
            return GCSUserFiles()
