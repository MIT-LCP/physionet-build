from unittest import skipIf

from decouple import config
from django.test import TestCase, override_settings
from google.api_core.client_options import ClientOptions
from google.auth.credentials import AnonymousCredentials
from google.cloud.exceptions import NotFound
from google.cloud.storage import Blob, Bucket, Client
from physionet.gcs import GCSObject, GCSObjectException
from physionet.settings.base import StorageTypes

TEST_GCS_INTEGRATION = config('TEST_GCS_INTEGRATION', default=True, cast=bool)
GCS_HOST = config('GCS_HOST', default=None)


@skipIf(
    (GCS_HOST is None or not TEST_GCS_INTEGRATION),
    'Test GCS-backend integration only on dockerized CI/CD pipeline.',
)
@override_settings(
    STORAGE_TYPE=StorageTypes.GCP,
    DEFAULT_FILE_STORAGE='physionet.storage.MediaStorage',
    STATICFILES_STORAGE='physionet.storage.StaticStorage',
    GCP_STORAGE_BUCKET_NAME='physionet-media',
    GCP_STATIC_BUCKET_NAME='physionet-static',
    GS_PROJECT_ID='test_project_id',
    GCP_BUCKET_LOCATION='us-west1',
)
class TestGCSObject(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gcs_server_endpoint = f'http://{config("GCS_HOST", default="gcs")}:4443'
        cls.bucket_name = 'test'
        cls.path = 'physionet/users/admin/profile.jpg'

    def tearDown(self):
        try:
            self._clear_gcs_bucket(self.bucket_name)
        except NotFound:
            pass

    def _clear_gcs_bucket(self, name):
        self._get_gcs_client().get_bucket(name).delete(force=True)

    def _get_gcs_client(self):
        return Client(
            project="test_project_id",
            credentials=AnonymousCredentials(),
            client_options=ClientOptions(api_endpoint=self.gcs_server_endpoint),
        )

    def _monkeypatch_gcsobject(self, gcs_object):
        gcs_object._storage._client = self._get_gcs_client()
        return gcs_object

    @override_settings(STORAGE_TYPE=StorageTypes.LOCAL)
    def test_init_raises_exception_when_storage_types_is_local(self):
        self.assertRaises(GCSObjectException, GCSObject, self.path)

    @override_settings(STORAGE_TYPE=StorageTypes.GCP)
    def test_init_when_storage_type_is_gcp(self):
        gcs_object = self._monkeypatch_gcsobject(GCSObject(self.path))

        self.assertEqual(gcs_object.bucket.name, 'physionet')
        self.assertEqual(gcs_object._object_name, 'users/admin/profile.jpg')

    def test_repr(self):
        gcs_object = self._monkeypatch_gcsobject(GCSObject(self.path))

        self.assertEqual(
            repr(gcs_object),
            'GCSObject(Bucket=physionet, Object="users/admin/profile.jpg")',
        )

    def test_bucket_property_return_bucket_proper_object(self):
        gcs_object = self._monkeypatch_gcsobject(GCSObject(self.path))

        self.assertIsInstance(gcs_object.bucket, Bucket)
        self.assertEqual(gcs_object.bucket.name, 'physionet')

    def test_blob_property_return_proper_object(self):
        gcs_object = self._monkeypatch_gcsobject(GCSObject(self.path))

        self.assertIsInstance(gcs_object.blob, Blob)
        self.assertEqual(gcs_object.blob.name, 'users/admin/profile.jpg')

    def test_mkdir_makes_directories(self):
        # GIVEN
        gcs_object = self._monkeypatch_gcsobject(GCSObject('test/dir1/dir2/'))
        gcs_object.client.create_bucket('test')

        # WHEN
        gcs_object.mkdir()

        # THEN
        self.assertTrue(gcs_object.bucket.get_blob('dir1/dir2/'))

    def test_mkdir_doesnt_work_when_object_name_is_taken(self):
        # GIVEN
        gcs_object = self._monkeypatch_gcsobject(GCSObject('test/dir1/dir2/'))
        gcs_object.client.create_bucket('test')
        gcs_object.mkdir()

        # WHEN + THEN
        self.assertRaises(GCSObjectException, gcs_object.mkdir)

    def test_size_when_object_is_file(self):
        # GIVEN
        gcs_object = self._monkeypatch_gcsobject(GCSObject('test/dir1/notes.txt'))
        gcs_object.client.create_bucket('test')
        gcs_object.upload_from_string('content')

        # WHEN + THEN
        self.assertEqual(gcs_object.size(), len('content'))

    def test_size_when_object_is_directory(self):
        # GIVEN
        gcs_object = self._monkeypatch_gcsobject(GCSObject('test/dir1/'))
        gcs_object_1 = self._monkeypatch_gcsobject(GCSObject('test/dir1/notes1.txt'))
        gcs_object_2 = self._monkeypatch_gcsobject(GCSObject('test/dir1/notes2.txt'))

        # create a bucket
        gcs_object.client.create_bucket('test')

        # put files into a bucket
        gcs_object_1.upload_from_string('content')
        gcs_object_2.upload_from_string('content')

        # WHEN + THEN
        self.assertEqual(gcs_object.size(), len('content') * 2)

    def test_rm_deletes_all_files_in_directory_when_object_is_directory(self):
        # GIVEN
        gcs_object = self._monkeypatch_gcsobject(GCSObject('test/dir1/'))
        gcs_object_1 = self._monkeypatch_gcsobject(GCSObject('test/dir1/notes1.txt'))
        gcs_object_2 = self._monkeypatch_gcsobject(GCSObject('test/dir1/notes2.txt'))

        # create a bucket
        gcs_object.client.create_bucket('test')

        # put files into a bucket
        gcs_object_1.upload_from_string('content')
        gcs_object_2.upload_from_string('content')

        # WHEN
        gcs_object.rm()

        # THEN
        self.assertEqual(gcs_object.size(), 0)

    def test_rm_removes_file_when_object_is_file(self):
        # GIVEN
        gcs_object = self._monkeypatch_gcsobject(GCSObject('test/dir/file.jpg'))
        gcs_object.client.create_bucket('test')
        gcs_object.upload_from_string('content')

        # WHEN
        gcs_object.rm()

        # THEN
        dir_ = self._monkeypatch_gcsobject(self._monkeypatch_gcsobject(GCSObject('test/dir/')))
        self.assertEqual(dir_.size(), 0)

    def test_cp_copies_file_to_directory(self):
        # GIVEN
        gcs_object = self._monkeypatch_gcsobject(GCSObject('test/dir/file.jpg'))
        gcs_object_1 = self._monkeypatch_gcsobject(GCSObject('test/dir/'))

        # create a bucket
        gcs_object.client.create_bucket('test')

        # put a file into a bucket
        gcs_object.upload_from_string('content')

        # WHEN
        gcs_object_1.cp(self._monkeypatch_gcsobject(GCSObject('test/dir_copied/')))

        # THEN
        self.assertEqual(gcs_object_1.size(), len('content'))
        self.assertEqual(gcs_object.size(), len('content'))

    def test_mv_moves_file_when_object_is_file(self):
        # GIVEN
        gcs_object = self._monkeypatch_gcsobject(GCSObject('test/dir/file.jpg'))
        gcs_object_1 = self._monkeypatch_gcsobject(GCSObject('test/dir/'))
        gcs_object_2 = self._monkeypatch_gcsobject(GCSObject('test/dir_copied/'))

        # create a bucket
        gcs_object.client.create_bucket('test')

        # put a file into a bucket
        gcs_object.upload_from_string('content')

        # WHEN
        gcs_object_1.mv(self._monkeypatch_gcsobject(GCSObject('test/dir_copied/')))

        # THEN
        self.assertEqual(gcs_object_2.size(), len('content'))
        self.assertEqual(gcs_object.exists(), False)

    def test_rename_file(self):
        # GIVEN
        gcs_object = self._monkeypatch_gcsobject(GCSObject('test/file.jpg'))
        gcs_object.client.create_bucket('test')
        gcs_object.upload_from_string('content')

        gcs_object_renamed = self._monkeypatch_gcsobject(GCSObject('test/renamed.jpg'))

        # WHEN
        gcs_object.rename(gcs_object_renamed)

        # THEN
        self.assertFalse(gcs_object.exists())
        self.assertTrue(gcs_object_renamed.exists())
        self.assertEqual(gcs_object_renamed.size(), len('content'))
