import os
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from moto import mock_s3

from project.cloud.s3 import (
    check_s3_bucket_exists,
    create_s3_client,
    create_s3_server_access_log_bucket,
    get_bucket_name,
    has_s3_credentials,
    upload_project_to_S3,
)
from project.models import PublishedProject
from user.test_views import TestMixin


@override_settings(
    AWS_PROFILE='default',
    AWS_ACCOUNT_ID='123456789012',
    S3_OPEN_ACCESS_BUCKET='datashare-public',
    S3_SERVER_ACCESS_LOG_BUCKET='datashare-logs',
)
class TestS3(TestMixin):
    """
    Test cases for S3 project uploads.
    """
    maxDiff = None

    def setUp(self):
        super().setUp()

        # The following environment variables are used by boto3, and
        # should be set to avoid unpredictable behavior when testing.
        # They need to be set before calling mock_s3().  This list
        # might be incomplete.
        self.mock_env = mock.patch.dict(os.environ, {
            'AWS_SHARED_CREDENTIALS_FILE': os.path.join(
                settings.DEMO_FILE_ROOT, 'aws_credentials'),
            'AWS_PROFILE': settings.AWS_PROFILE,
            'AWS_ACCESS_KEY_ID': '',
            'AWS_SECRET_ACCESS_KEY': '',
            'AWS_SECURITY_TOKEN': '',
            'AWS_SESSION_TOKEN': '',
            'AWS_DEFAULT_REGION': '',
        })
        self.mock_env.start()
        self.mock_s3 = mock_s3()
        self.mock_s3.start()

    def tearDown(self):
        super().tearDown()
        self.mock_s3.stop()
        self.mock_env.stop()

    def test_s3_credentials(self):
        """
        Check that dummy credentials are configured for S3.
        """
        self.assertTrue(has_s3_credentials())

    def test_create_log_bucket(self):
        """
        Test creating an S3 bucket for server access logs.
        """
        create_s3_server_access_log_bucket()
        self.assert_bucket_is_not_public(settings.S3_SERVER_ACCESS_LOG_BUCKET)

    def test_upload_open_projects(self):
        """
        Test uploading open-access projects to S3.
        """
        create_s3_server_access_log_bucket()

        project1 = PublishedProject.objects.get(slug='demobsn',
                                                version='1.0')
        self.assertGreater(project1.compressed_storage_size, 0)

        project2 = PublishedProject.objects.get(slug='demowave',
                                                version='1.0.0')
        self.assertEqual(project2.compressed_storage_size, 0)

        self.assertFalse(check_s3_bucket_exists(project1))
        self.assertFalse(check_s3_bucket_exists(project2))

        upload_project_to_S3(project1)
        upload_project_to_S3(project2)

        self.assertTrue(check_s3_bucket_exists(project1))
        self.assertTrue(check_s3_bucket_exists(project2))

        s3 = create_s3_client()
        expected_files = {}
        for project in (project1, project2):
            bucket = get_bucket_name(project)
            self.assert_bucket_is_public(bucket)

            prefix = project.slug + '/' + project.version + '/'
            for subdir, _, files in os.walk(project.file_root()):
                for name in files:
                    path = os.path.join(subdir, name)
                    relpath = os.path.relpath(path, project.file_root())
                    expected_files[prefix + relpath] = os.path.getsize(path)

            if project.compressed_storage_size:
                zip_path = project.zip_name(full=True)
                zip_key = project.slug + '/' + project.zip_name(legacy=False)
                expected_files[zip_key] = os.path.getsize(zip_path)

        objects = s3.list_objects_v2(Bucket=bucket)
        bucket_files = {}
        for object_info in objects['Contents']:
            bucket_files[object_info['Key']] = object_info['Size']

        self.assertEqual(bucket_files, expected_files)

    def assert_bucket_is_public(self, bucket_name):
        """
        Check that a bucket exists and allows some form of public access.
        """
        s3 = create_s3_client()
        pab = s3.get_public_access_block(Bucket=bucket_name)
        conf = pab['PublicAccessBlockConfiguration']
        self.assertFalse(conf['BlockPublicAcls'])
        self.assertFalse(conf['IgnorePublicAcls'])
        self.assertFalse(conf['BlockPublicPolicy'])
        self.assertFalse(conf['RestrictPublicBuckets'])

    def assert_bucket_is_not_public(self, bucket_name):
        """
        Check that a bucket exists and does not allow public access.
        """
        s3 = create_s3_client()
        pab = s3.get_public_access_block(Bucket=bucket_name)
        conf = pab['PublicAccessBlockConfiguration']
        self.assertTrue(conf['BlockPublicAcls'])
        self.assertTrue(conf['IgnorePublicAcls'])
        self.assertTrue(conf['BlockPublicPolicy'])
        self.assertTrue(conf['RestrictPublicBuckets'])
