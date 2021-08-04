import os
from django.conf import settings
from google.cloud.exceptions import Conflict, NotFound
from google.cloud.storage import Client
from storages.backends.gcloud import GoogleCloudStorage
from project.utility import FileInfo, DirectoryInfo, readable_size


class ObjectPath(object):
    def __init__(self, path):
        self._client = None
        self._bucket = None

        try:
            normalized_path = os.path.normpath(path)
            self._bucket_name, self._key = normalized_path.split('/', 1)
        except ValueError:
            raise ValueError('path should specify the bucket and object key/prefix')

    def __repr__(self):
        return f"ObjectPath('{self.bucket_name}', '{self.key}')"

    @property
    def bucket_name(self):
        return self._bucket_name

    @property
    def key(self):
        if self._key == '':
            raise ValueError('object key cannot be empty')
        return self._key

    @property
    def dir_key(self):
        if self._key == '':
            return self._key
        return self._key + '/'

    @property
    def client(self):
        if self._client is None:
            self._client = GoogleCloudStorage().client
        return self._client

    @property
    def bucket(self):
        if self._bucket is None:
            self._bucket = self.client.get_bucket(self.bucket_name)
        return self._bucket

    @property
    def blob(self):
        return self.bucket.blob(self.key)

    @property
    def dir_blob(self):
        return self.bucket.blob(self.dir_key)

    def batch(self):
        return self.client.batch()

    def create_bucket(self):
        bucket = self.client.bucket(self.bucket_name)
        bucket.location = 'us-west1'
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True
        self.client.create_bucket(bucket)

    def create_bucket_if_needed(self):
        try:
            self.create_bucket()
        except Conflict:
            pass

    def put(self, data):
        self.blob.upload_from_string(data)

    def put_fileobj(self, file):
        self.blob.upload_from_file(file)

    def mkdir(self, **kwargs):
        self.dir_blob.upload_from_string('')

    def exists(self):
        return self.file_exists() or self.dir_exists()

    def file_exists(self):
        return self.blob.exists()

    def dir_exists(self):
        iterator = self.client.list_blobs(self.bucket_name, prefix=self.dir_key, max_results=1)
        return len(list(iterator)) > 0

    def dir_size(self):
        iterator = self.client.list_blobs(self.bucket_name, prefix=self.dir_key)
        return sum([obj.size for obj in iterator])

    def open(self, mode='rb'):
        storage = GoogleCloudStorage(bucket_name=self.bucket_name)
        return storage.open(self.key, mode=mode)

    def list_dir(self):
        iterator = self.client.list_blobs(self.bucket_name, prefix=self.dir_key, delimiter='/')
        blobs = list(iterator)
        prefixes = iterator.prefixes

        files = []
        dirs = []

        for blob in blobs:
            name = blob.name.replace(self.dir_key, '', 1)
            if name != '':
                size = readable_size(blob.size)
                modified = blob.updated.strftime("%Y-%m-%d")
                files.append(FileInfo(name, size, modified))

        for prefix in prefixes:
            dirs.append(DirectoryInfo(prefix.replace(self.dir_key, '', 1)[:-1]))

        files.sort()
        dirs.sort()

        return files, dirs

    def url(self):
        storage = GoogleCloudStorage(bucket_name=self.bucket_name)
        return storage.url(self.key)

    def rm(self):
        try:
            self.rm_file()
        except NotFound:
            pass

        self.rm_dir()

    def rm_file(self):
        self.blob.delete()

    def rm_dir(self):
        blobs = list(self.client.list_blobs(self.bucket_name, prefix=self.dir_key))
        self.bucket.delete_blobs(blobs=blobs)

    def cp(self, other):
        try:
            self.cp_file(other)
        except NotFound:
            pass

        self.cp_dir(other)

    def cp_file(self, other):
        self.bucket.copy_blob(self.blob, other.bucket, new_name=other.key)

    def cp_dir(self, other, ignored_files=[]):
        ignored_files = [os.path.join(self.dir_key, f) for f in ignored_files]

        iterator = self.client.list_blobs(self.bucket_name, prefix=self.dir_key)
        try:
            with self.batch():
                for blob in iterator:
                    if blob.name in ignored_files:
                        continue
                    new_name = blob.name.replace(self.dir_key, other.dir_key, 1)
                    self.bucket.copy_blob(blob, other.bucket, new_name=new_name)
        except ValueError: # thrown when there are no batch requests
            pass

    def mv(self, other):
        self.cp(other)
        self.rm()

    def mv_file(self, other):
        self.cp_file(other)
        self.rm_file()

    def mv_dir(self, other):
        self.cp_dir(other)
        self.rm_dir()
