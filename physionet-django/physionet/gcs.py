import os

from django.conf import settings
from django.core.files.storage import get_storage_class
from physionet.settings.base import StorageTypes
from storages.backends.gcloud import GoogleCloudStorage


class GCSObjectException(Exception):
    pass


class GCSObject:
    """
    The representation of an object in Google Cloud Storage.
    This class defines a set of useful operations which can be applied to the GCS object.

    Path has to be passed to the constructor in the following format:
    path="{bucket_name}/{object_name}"
    Paths ending in '/' point to a directory.

    Example 1:
        gcs_file = GCSObject(path="physionet/europe/cannes.jpg")
            bucket = physionet
            object = europe/cannes.jpg

    Example 2:
        gcs_dir = GCSObject(path="physionet/projectfiles/")
            bucket = physionet
            object = projectfiles/
    """

    def __init__(self, path, storage_klass=None):
        if settings.STORAGE_TYPE != StorageTypes.GCP and storage_klass is None:
            raise GCSObjectException(
                f"The default `STORAGE_TYPE` is not set to GCP. You can pass custom `storage_klass`."
                f"{self.__class__.__name__} works only with Storage class that can manage files stored in GCS."
            )
        self._storage, self._object_name = self._retrieve_data_from_path(path, storage_klass)

    def __repr__(self):
        return f'{self.__class__.__name__}(Bucket={self.bucket.name}, Object="{self.name}")'

    @property
    def bucket(self):
        """Return the bucket"""
        return self._storage.bucket

    @property
    def blob(self):
        """Return the blob"""
        return self._storage.bucket.blob(self.name)

    @property
    def url(self):
        """Return the url"""
        return self._storage.url(self.name)

    @property
    def client(self):
        """Return the client"""
        return self._storage.client

    @property
    def name(self):
        """Return the name"""
        return self._object_name

    @property
    def local_name(self):
        """Return the relative name inside the bucket"""
        return '' if self.name == '/' else self.name

    def open(self, mode):
        """Open the location with the given mode"""
        return self._storage.open(self.name, mode=mode)

    def upload_from_string(self, content):
        """Upload the contents from the provided string"""
        self.blob.upload_from_string(content)

    def upload_from_file(self, file):
        """Upload the contents from a file object"""
        self.blob.upload_from_file(file)

    def exists(self):
        """Check if blob exists"""
        return True if self.bucket.get_blob(self.name) else False

    def mkdir(self):
        """An empty object in GCS is a zero-byte object with a name ending in `/`."""
        if not self.is_dir():
            raise GCSObjectException(f'The {repr(self)} is not a directory.')

        if self.exists():
            raise GCSObjectException(f'The name `{self.name}` is already taken.')

        self.blob.upload_from_string('')

    def size(self):
        """Size of the object/all objects in the dictionary, in bytes."""
        if self.is_dir():
            return sum(obj.size for obj in self.bucket.list_blobs(prefix=self.local_name))

        file = self.bucket.get_blob(self.blob.name)
        if not file:
            raise GCSObjectException('The specified file does not exist')
        return file.size

    def ls(self, delimiter=None):
        """List directory contents. Returns an iterator of blobs."""
        if not self.is_dir():
            raise GCSObjectException(f'The {repr(self)} is not a directory.')

        return self.bucket.list_blobs(prefix=self.local_name, delimiter=delimiter)

    def rm(self):
        """Remove"""
        if self.is_dir():
            self.bucket.delete_blobs(list(self.ls()))
        else:
            self.bucket.delete_blob(self.name)

    def cp(self, gcs_obj, ignored_files=None):
        """Copy"""
        if not gcs_obj.is_dir():
            raise GCSObjectException('The target path must point on directory.')

        if not self.is_dir() and ignored_files:
            raise GCSObjectException('`ignored_files` does not work when copying a file.')

        if self.is_dir():
            self._cp_dir(gcs_obj, ignored_files)
        else:
            self._cp_file(gcs_obj)

    def mv(self, gcs_obj, ignored_files=None):
        """Move"""
        if not gcs_obj.is_dir():
            raise GCSObjectException(
                'The target path must point on directory. If you want to rename a file use `.rename()` method.'
            )

        if self.is_dir():
            self._cp_dir(gcs_obj, ignored_files=ignored_files)
        else:
            self._cp_file(gcs_obj)

        self.rm()

    def rename(self, gcs_obj):
        """Rename"""
        if self.is_dir():
            self.cp_dir_content(gcs_obj, ignored_files=None)
            self.rm()
        else:
            self.bucket.rename_blob(self.blob, new_name=gcs_obj.name)

    def is_dir(self):
        """Check if the object is a directory"""
        return self.name.endswith('/')

    def get_filename(self):
        """Return the filename from the path"""
        if self.is_dir():
            return self.name.split('/')[-2] + '/'
        return self.name.split('/')[-1]

    def _cp_file(self, gcs_obj):
        """Copy file"""
        self.bucket.copy_blob(
            self.blob,
            gcs_obj.bucket,
            new_name=gcs_obj.name + self.get_filename(),
        )

    def cp_dir_content(self, gcs_obj, ignored_files):
        """Copies only the content of the directory."""
        self._cp_dir(gcs_obj, ignored_files, True)

    def _cp_dir(self, gcs_obj, ignored_files, copy_content_only=False):
        """
        Copies a directory with its files.
        If 'copy_content_only' is True - the contents of the directory are copied rather than the directory itself.
        """
        if ignored_files is None:
            ignored_files = []
        else:
            ignored_files = [os.path.join(self.local_name, f) for f in ignored_files]

        relative_dir = '' if copy_content_only else self.get_filename()
        try:
            for blob in self.ls():
                if blob.name in ignored_files:
                    continue

                new_name = (
                    gcs_obj.name + relative_dir + blob.name.replace(os.path.commonprefix([self.name, blob.name]), '')
                )
                if new_name == '/':
                    continue

                self.bucket.copy_blob(
                    blob,
                    gcs_obj.bucket,
                    new_name=new_name.lstrip('/'),
                )
        except ValueError:
            pass

    def _retrieve_data_from_path(self, path, storage_klass):
        """
        path="test-bucket/" -> test-bucket, "/"
        path="test-bucket/dir/image.jpg" -> test-bucket, "dir/image.jpg"
        path="test-bucket" -> raise GCSObjectException
        """
        if storage_klass is None:
            storage_klass = settings.DEFAULT_FILE_STORAGE

        add_slash = path.endswith('/')
        path = os.path.normpath(path).split('/', 1)
        try:
            bucket_name, object_name = path
        except ValueError:
            bucket_name = path[0]
            if not add_slash:
                raise GCSObjectException('The provided path does not indicate a resource in the bucket.')
            object_name = '/'
        else:
            if add_slash:
                object_name += '/'

        return (
            get_storage_class(storage_klass)(bucket_name=bucket_name),
            object_name,
        )


def create_bucket(name):
    client = GoogleCloudStorage().client
    bucket = client.bucket(name)
    bucket.location = settings.GCP_BUCKET_LOCATION
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
    client.create_bucket(bucket)


def delete_bucket(name):
    client = GoogleCloudStorage().client
    bucket = client.bucket(name)
    bucket.delete(force=True)
