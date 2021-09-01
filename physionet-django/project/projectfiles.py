import abc
import os

from django.conf import settings
from google.cloud.exceptions import NotFound
from storages.backends.gcloud import GoogleCloudStorage

from physionet.settings.base import StorageTypes
from project.utility import remove_items, write_uploaded_file, rename_file, move_items, list_items, get_file_info, \
    get_directory_info, readable_size, FileInfo, DirectoryInfo, clear_directory


class BaseProjectFiles(abc.ABC):
    """Base class that defines all project file operations."""

    @abc.abstractmethod
    def mkdir(self, path):
        raise NotImplementedError

    @abc.abstractmethod
    def rm(self, path):
        raise NotImplementedError

    @abc.abstractmethod
    def fwrite(self, path, content):
        raise NotImplementedError

    @abc.abstractmethod
    def fput(self, path, file):
        raise NotImplementedError

    @abc.abstractmethod
    def rename(self, source_path, target_path):
        raise NotImplementedError

    @abc.abstractmethod
    def mv(self, source_path, target_path):
        raise NotImplementedError

    @abc.abstractmethod
    def open(self, path, mode='rb'):
        raise NotImplementedError

    @abc.abstractmethod
    def get_project_directory_content(self, path, subdir, file_display_url, file_url):
        raise NotImplementedError

    @abc.abstractmethod
    def cp_dir(self, source_path, target_path, ignored_files=None):
        raise NotImplementedError

    @abc.abstractmethod
    def raw_url(self, project, path):
        raise NotImplementedError

    @abc.abstractmethod
    def download_url(self, project, path):
        raise NotImplementedError

    @abc.abstractmethod
    def rm_dir(self, path, remove_zip):
        raise NotImplementedError


class LocalProjectFiles(BaseProjectFiles):
    def __init__(self, project_path):
        self._project_path = project_path

    def mkdir(self, path):
        os.mkdir(path)

    def rm(self, path):
        remove_items([path], ignore_missing=False)

    def fwrite(self, path, content):
        with open(path, 'w') as outfile:
            outfile.write(content)

    def fput(self, path, file):
        write_uploaded_file(
            file=file,
            overwrite=False,
            write_file_path=os.path.join(path, file.name),
        )

    def rename(self, source_path, target_path):
        rename_file(source_path, target_path)

    def mv(self, source_path, target_path):
        move_items([source_path], target_path)

    def open(self, path, mode='rb'):
        infile = open(path, mode)
        size = os.stat(infile.fileno()).st_size

        return infile, size

    def get_project_directory_content(self, path, subdir, file_display_url, file_url):
        file_names, dir_names = list_items(path)
        display_files, display_dirs = [], []

        # Files require desciptive info and download links
        for file in file_names:
            file_info = get_file_info(os.path.join(path, file))
            file_info.url = file_display_url(subdir=subdir, file=file)
            file_info.raw_url = file_url(subdir=subdir, file=file)
            file_info.download_url = file_info.raw_url + '?download'
            display_files.append(file_info)

        # Directories require links
        for dir_name in dir_names:
            dir_info = get_directory_info(os.path.join(path, dir_name))
            dir_info.full_subdir = os.path.join(subdir, dir_name)
            display_dirs.append(dir_info)

        return display_files, display_dirs

    def cp_dir(self, source_path, target_path, ignored_files=None):
        os.mkdir(target_path)
        for (directory, subdirs, files) in os.walk(source_path):
            rel_dir = os.path.relpath(directory, source_path)
            destination = os.path.join(target_path, rel_dir)
            for d in subdirs:
                try:
                    os.mkdir(os.path.join(destination, d))
                except FileExistsError:
                    pass
            for f in files:
                # Skip linking files that are automatically generated
                # during publication.
                if (directory == source_path and f in ignored_files):
                    continue
                try:
                    os.link(os.path.join(directory, f),
                            os.path.join(destination, f))
                except FileExistsError:
                    pass

    def raw_url(self, project, path):
        return project.file_url('', path)

    def download_url(self, project, path):
        return self.raw_url(project, path) + '?download'

    def rm_dir(self, path, remove_zip):
        clear_directory(path)
        remove_zip()


class GCSProjectFiles(BaseProjectFiles):
    def __init__(self, project_path):
        self._project_path = project_path

        # TODO: what if we want to use different bucket?
        # TODO: refactor?
        self._gcs = GoogleCloudStorage(
            bucket_name=os.path.normpath(self._project_path.split('/', 1)[0])
        )

    def mkdir(self, path):
        path = self._local_filesystem_path_to_gcs_path(path)
        if self._gcs.exists(path):
            raise FileExistsError

        if path[-1] != '/':
            path += '/'

        self._gcs.bucket.blob(path).upload_from_string('')

    def rm(self, path):
        try:
            self._gcs.bucket.blob(self._local_filesystem_path_to_gcs_path(path)).delete()
        except NotFound:
            pass

        self.rm_dir(path, None)

    def rm_dir(self, path, remove_zip):
        path = self._local_filesystem_path_to_gcs_path(path)

        blobs = list(self._gcs.bucket.list_blobs(prefix=path))
        self._gcs.bucket.delete_blobs(blobs=blobs)

    def fwrite(self, path, content):
        path = self._local_filesystem_path_to_gcs_path(path)
        if self._gcs.exists(path):
            raise FileExistsError

        self._gcs.bucket.blob(path).upload_from_string(content)

    def fput(self, path, file):
        path = os.path.join(self._local_filesystem_path_to_gcs_path(path), file.name)
        if self._gcs.exists(path):
            raise FileExistsError

        self._gcs.bucket.blob(path).upload_from_file(file)

    def rename(self, source_path, target_path):
        self.mv(source_path, target_path)

    def mv(self, source_path, target_path):
        try:
            self._mv_file(source_path, target_path)
        except NotFound:
            self.cp_dir(source_path, target_path)
            blobs = list(self._gcs.bucket.list_blobs(prefix=source_path))
            self._gcs.bucket.delete_blobs(blobs=blobs)

    def open(self, path, mode='rb'):
        path = self._local_filesystem_path_to_gcs_path(path)
        infile = self._gcs.open(path, mode=mode)
        return infile, infile.size

    def get_project_directory_content(self, path, subdir, file_display_url, file_url):
        files, dirs = self._list_dir(path)

        for file in files:
            file.url = file_display_url(subdir=subdir, file=file.name)
            file.raw_url = self._url(os.path.join(self._local_filesystem_path_to_gcs_path(path), file.name))
            file.download_url = file.raw_url

        for dir in dirs:
            dir.full_subdir = os.path.join(subdir, dir.name)

        return files, dirs

    def _mv_file(self, source_path, target_path):
        source_path = self._local_filesystem_path_to_gcs_path(source_path)
        target_path = self._local_filesystem_path_to_gcs_path(target_path)

        source_blob = self._gcs.bucket.blob(source_path)

        self._gcs.bucket.copy_blob(source_blob, self._gcs.bucket, new_name=target_path)
        self._gcs.bucket.delete_blob(source_path)

    def cp_dir(self, source_path, target_path, ignored_files=None):
        source_path = self._dir_path(self._local_filesystem_path_to_gcs_path(source_path))
        target_path = self._dir_path(self._local_filesystem_path_to_gcs_path(target_path))

        if ignored_files is None:
            ignored_files = []
        else:
            ignored_files = [os.path.join(source_path, f) for f in ignored_files]

        iterator = self._gcs.bucket.list_blobs(prefix=source_path, delimiter='/')
        try:
            with self._gcs.client.batch():
                for blob in iterator:
                    if blob.name in ignored_files:
                        continue
                    new_name = blob.name.replace(source_path, target_path, 1)
                    self._gcs.bucket.copy_blob(blob, self._gcs.bucket, new_name=new_name)
        except ValueError:
            pass

    def raw_url(self, project, path):
        path_to_file = self._local_filesystem_path_to_gcs_path(os.path.join(project.file_root(), path))
        return self._url(path_to_file)

    def download_url(self, project, path):
        return self.raw_url(project, path)

    def _url(self, path):
        return self._gcs.url(path)

    def _list_dir(self, path):
        path = self._dir_path(self._local_filesystem_path_to_gcs_path(path))

        iterator = self._gcs.bucket.list_blobs(prefix=path, delimiter='/')
        blobs = list(iterator)
        prefixes = iterator.prefixes

        files = []
        dirs = []

        for blob in blobs:
            name = blob.name.replace(path, '', 1)
            if name != '':
                size = readable_size(blob.size)
                modified = blob.updated.strftime("%Y-%m-%d")
                files.append(FileInfo(name, size, modified))

        for prefix in prefixes:
            dirs.append(DirectoryInfo(prefix.replace(path, '', 1)[:-1]))

        files.sort()
        dirs.sort()

        return files, dirs

    def _dir_path(self, path):
        return path + '/' if path[-1] != '/' else path

    def _local_filesystem_path_to_gcs_path(self, path):
        return os.path.normpath(path).split('/', 1)[1]


class ProjectFiles:
    def __new__(cls, project_path):
        if settings.STORAGE_TYPE == StorageTypes.LOCAL:
            return LocalProjectFiles(project_path)
        elif settings.STORAGE_TYPE == StorageTypes.GCP:
            return GCSProjectFiles(project_path)
