import os

from django.conf import settings
from django.shortcuts import redirect
from google.cloud.exceptions import Conflict, NotFound
from physionet.gcs import GCSObject, GCSObjectException, create_bucket, delete_bucket
from project.projectfiles.base import BaseProjectFiles
from project.quota import GCSQuotaManager
from project.utility import DirectoryInfo, FileInfo, readable_size


class GCSProjectFiles(BaseProjectFiles):
    @property
    def file_root(self):
        return settings.GCP_STORAGE_BUCKET_NAME

    def mkdir(self, path):
        path = self._dir_path(path)

        try:
            GCSObject(path).mkdir()
        except GCSObjectException:
            raise FileExistsError

    def rm(self, path):
        try:
            GCSObject(path).rm()
        except NotFound:
            GCSObject(self._dir_path(path)).rm()

    def rm_dir(self, path, remove_zip=None):
        path = self._dir_path(path)
        GCSObject(path).rm()

    def fwrite(self, path, content):
        gcs_object = GCSObject(path)
        if gcs_object.exists():
            raise FileExistsError

        gcs_object.upload_from_string(content)

    def fput(self, path, file):
        gcs_object = GCSObject(os.path.join(path, file.name))
        if gcs_object.exists():
            raise FileExistsError

        gcs_object.upload_from_file(file)

    def rename(self, source_path, target_path):
        gcs_obj = GCSObject(source_path)
        if not gcs_obj.exists():
            gcs_obj = GCSObject(self._dir_path(source_path))
            target_path = self._dir_path(target_path)

        gcs_obj.rename(GCSObject(target_path))

    def cp_file(self, source_path, target_path):
        gcs_obj = GCSObject(source_path)
        if not gcs_obj.exists():
            gcs_obj = GCSObject(self._dir_path(source_path))
            target_path = self._dir_path(target_path)

        gcs_obj.cp(GCSObject(target_path))

    def mv(self, source_path, target_path):
        source_path = source_path
        target_path = self._dir_path(target_path)

        try:
            GCSObject(source_path).mv(GCSObject(target_path))
        except GCSObjectException:
            GCSObject(self._dir_path(source_path)).mv(GCSObject(target_path))

    def open(self, path, mode='rb'):
        return GCSObject(path).open(mode)

    def get_project_directory_content(self, path, subdir, file_display_url, file_url):
        files, dirs = self._list_dir(path)

        for file in files:
            file.url = file_display_url(subdir=subdir, file=file.name)
            file.raw_url = self._url(os.path.join(path, file.name))
            file.download_url = file.raw_url

        for dir in dirs:
            dir.full_subdir = os.path.join(subdir, dir.name)

        return files, dirs

    def cp_dir(self, source_path, target_path, ignored_files=None):
        source_path = self._dir_path(source_path)
        target_path = self._dir_path(target_path)

        GCSObject(source_path).cp_dir_content(GCSObject(target_path), ignored_files=ignored_files)

    def raw_url(self, project, path):
        return self._url(os.path.join(project.file_root(), path))

    def rmtree(self, path):
        path = self._dir_path(path)

        GCSObject(path).rm()

    def download_url(self, project, path):
        return self.raw_url(project, path)

    def publish_initial(self, active_project, published_project):
        bucket_name = published_project.project_file_root()
        create_bucket(bucket_name)

        try:
            active_project_path = self._dir_path(active_project.file_root())
            published_project_path = self._dir_path(published_project.file_root())
            GCSObject(active_project_path).cp_dir_content(GCSObject(published_project_path), None)
        except BaseException:
            delete_bucket(bucket_name)
            raise

    def publish_complete(self, active_project, published_project):
        self.rm_dir(active_project.file_root())

    def publish_rollback(self, active_project, published_project):
        delete_bucket(published_project.project_file_root())

    def get_project_file_root(self, slug, version, access_policy, klass):
        return f'{slug}-{version}.{settings.GCP_DOMAIN}'

    def get_file_root(self, slug, version, access_policy, klass):
        return self.get_project_file_root(slug, version, access_policy, klass)

    def project_quota_manager(self, project):
        allowance = project.core_project.storage_allowance
        published = project.core_project.total_published_size
        limit = allowance - published

        quota_manager = GCSQuotaManager(project.file_root())
        quota_manager.set_limits(bytes_hard=limit, bytes_soft=limit)
        return quota_manager

    def published_project_storage_used(self, project):
        return self._storage_used(project)

    def get_zip_file_size(self, project):
        return 0

    def make_zip(self, project):
        """Not implemented for GCS storage backend."""
        return None

    def make_checksum_file(self, project):
        """Not implemented for GCS storage backend."""
        return None

    def can_make_zip(self):
        return False

    def can_make_checksum(self):
        return False

    def is_lightwave_supported(self):
        return False

    def has_wfdb_files(self, project):
        return False

    def is_wget_supported(self):
        return False

    def serve_file_field(self, field):
        return redirect(field.url)

    def _storage_used(self, project):
        return GCSObject(self._dir_path(project.file_root())).size()

    def _url(self, path):
        return GCSObject(path).url

    def _list_dir(self, path):
        path = self._dir_path(path)

        iterator = GCSObject(path).ls(delimiter='/')
        _, object_name = self._local_filesystem_path_to_gcs_path(path)
        object_name = self._dir_path(object_name)

        blobs = list(iterator)
        prefixes = iterator.prefixes

        files = []
        dirs = []

        for blob in blobs:
            name = blob.name.replace(object_name, '', 1)
            if name != '':
                size = readable_size(blob.size)
                modified = blob.updated.strftime("%Y-%m-%d")
                files.append(FileInfo(name, size, modified))

        for prefix in prefixes:
            dirs.append(DirectoryInfo(prefix.replace(object_name, '', 1)[:-1]))

        files.sort()
        dirs.sort()

        return files, dirs

    def _dir_path(self, path):
        return path if path == '' or path.endswith('/') else path + '/'

    def _local_filesystem_path_to_gcs_path(self, path):
        bucket_name, *object_name = os.path.normpath(path).split('/', 1)

        object_name = object_name[0] if object_name else ''

        return bucket_name, object_name
