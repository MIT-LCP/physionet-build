import os

from django.conf import settings
from google.cloud.exceptions import NotFound
from google.cloud.storage import Client
from project.utility import DirectoryInfo, FileInfo, readable_size
from storages.backends.gcloud import GoogleCloudStorage


def get_client():
    return GoogleCloudStorage().client


class ObjectPath(object):
    def __init__(self, path):
        self._client = None
        self._bucket = None

        try:
            normalized_path = path.normpath(path)
            self._bucket_name, self._key = normalized_path.split('/', 1)
        except ValueError:
            raise ValueError('path should specify the bucket an object key/prefix')

    def __repr__(self):
        return f"ObjectPath('{self.bucket_name()}', '{self.key()}')"

    def bucket_name(self):
        return self._bucket_name

    def key(self):
        if self._key == '':
            raise ValueError('object key cannot be empty')
        return self._key

    def dir_key(self):
        if self._key == '':
            return self._key
        return self._key + '/'

    def client(self):
        if self._client is None:
            self._client = get_client()
        return self._client

    def bucket(self):
        if self._bucket is None:
            self._bucket = self.client().get_bucket(self.bucket_name())
        return self._bucket

    def blob(self):
        return self.bucket().blob(self.key())

    def dir_blob(self):
        return self.bucket().blob(self.dir_key())

    def put(self, data):
        bucket = self.bucket()
        blob = bucket.blob(self.key())
        blob.upload_from_string(data)

    def put_fileobj(self, file):
        bucket = self.bucket()
        blob = bucket.blob(self.key())
        blob.upload_from_file(file)

    def mkdir(self, **kwargs):
        bucket = self.bucket()
        blob = bucket.blob(self.dir_key())
        blob.upload_from_string('')

    def exists(self):
        return self.file_exists() or self.dir_exists()

    def file_exists(self):
        bucket = self.bucket()
        blob = bucket.blob(self.key())
        return blob.exists()

    def dir_exists(self):
        iterator = self.client().list_blobs(self.bucket_name(), prefix=self.dir_key(), max_results=1)
        return len(list(iterator)) > 0

    def dir_size(self):
        iterator = self.client().list_blobs(self.bucket_name(), prefix=self.dir_key())
        return sum([obj.size for obj in iterator])

    def open(self, mode='rb'):
        storage = GoogleCloudStorage(bucket_name=self.bucket_name())
        return storage.open(self.key(), mode=mode)

    def list_dir(self):
        iterator = self.client().list_blobs(self.bucket_name(), prefix=self.dir_key(), delimiter='/')
        blobs = list(iterator)
        prefixes = iterator.prefixes

        files = []
        dirs = []

        for blob in blobs:
            name = blob.name.replace(self.dir_key(), '', 1)
            if name != '':
                size = readable_size(blob.size)
                modified = blob.updated.strftime("%Y-%m-%d")
                files.append(FileInfo(name, size, modified))

        for prefix in prefixes:
            dirs.append(DirectoryInfo(prefix.replace(self.dir_key(), '', 1)[:-1]))

        files.sort()
        dirs.sort()

        return files, dirs

    def url(self):
        storage = GoogleCloudStorage(bucket_name=self.bucket_name())
        return storage.url(self.key())

    def rm(self):
        try:
            self.rm_file()
        except NotFound:
            pass

        self.rm_dir()

    def rm_file(self):
        self.blob().delete()

    def rm_dir(self):
        blobs = list(self.client().list_blobs(self.bucket_name(), prefix=self.dir_key()))
        self.bucket().delete_blobs(blobs=blobs)

    def cp(self, other):
        try:
            self.cp_file(other)
        except NotFound:
            pass

        self.cp_directory(other)

    def cp_file(self, other):
        self.bucket().copy_blob(self.blob(), other.bucket(), new_name=other.key())

    def cp_directory(self, other):
        iterator = self.client().list_blobs(self.bucket_name(), prefix=self.dir_key())
        for blob in iterator:
            new_name = blob.name.replace(self.dir_key(), other.dir_key(), 1)
            self.bucket().copy_blob(blob, other.bucket(), new_name=new_name)

    def mv(self, other):
        self.cp(other)
        self.rm()

    def mv_file(self, other):
        self.cp_file(other)
        self.rm_file()

    def mv_dir(self, other):
        self.cp_dir(other)
        self.rm_dir()
