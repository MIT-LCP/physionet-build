import os
import re
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from moto import (
    mock_s3,
    mock_s3control,
)

from project.authorization.access import can_view_project_files
from project.cloud.s3 import (
    check_s3_bucket_exists,
    create_s3_client,
    create_s3_control_client,
    create_s3_server_access_log_bucket,
    get_bucket_name,
    has_s3_credentials,
    upload_project_to_S3,
    disable_project_access_in_s3,
    restore_project_access_in_s3,
)
from project.models import (
    AWS,
    DUASignature,
    PublishedProject,
)
from user.models import (
    User,
    CloudInformation,
    Profile,
    Training,
    TrainingStatus,
)
from user.test_views import TestMixin


@override_settings(
    AWS_PROFILE='default',
    AWS_ACCOUNT_ID='123456789012',
    S3_OPEN_ACCESS_BUCKET='datashare-public',
    S3_SERVER_ACCESS_LOG_BUCKET='datashare-logs',
    S3_CONTROLLED_ACCESS_BUCKET='datashare-protected',
    S3_OPEN_ACCESS_BUCKET_WITH_LOGIN='datashare-geo-restricted',
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
        self.mock_s3control = mock_s3control()
        self.mock_s3control.start()

        self.user_counter = 1

    def tearDown(self):
        super().tearDown()
        self.mock_s3.stop()
        self.mock_s3control.stop()
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
        self.assert_bucket_is_public(get_bucket_name(project1))
        self.assert_project_files_uploaded([project1, project2])

    def test_reupload_open_project(self):
        """
        Test re-uploading a project after modifying its published content.
        """
        create_s3_server_access_log_bucket()

        project = PublishedProject.objects.get(slug='demobsn', version='1.0')

        # Create files of various sizes to test multi-part uploads.
        os.chmod(project.file_root(), 0o755)
        for size_mb in [0, 8, 16, 17.1]:
            path = os.path.join(project.file_root(), str(size_mb))
            with open(path, 'wb') as f:
                f.write(b'x' * int(size_mb * 1024 * 1024))

        # Upload the project.
        upload_project_to_S3(project)

        # List the objects that were uploaded, and add a custom tag to each.
        s3 = create_s3_client()
        bucket = get_bucket_name(project)
        objects = s3.list_objects_v2(Bucket=bucket)
        custom_tagset = [{'Key': 'test-reupload', 'Value': '1'}]
        for object_info in objects['Contents']:
            s3.put_object_tagging(
                Bucket=bucket, Key=object_info['Key'],
                Tagging={'TagSet': custom_tagset},
            )

        # Modify some existing files.
        alter_paths = ['data1.txt', 'scripts/lib.py']
        for path in alter_paths:
            os.chmod(os.path.join(project.file_root(), path), 0o644)
            with open(os.path.join(project.file_root(), path), 'a') as f:
                f.write('# additional content\n')

        # Re-upload the project.  This should update only the files
        # that were modified above.
        project = PublishedProject.objects.get(slug='demobsn', version='1.0')
        upload_project_to_S3(project)

        # All of the objects that were not modified should still have
        # the custom tag; modified objects should have been replaced
        # and their tags should be empty.
        project_prefix = project.slug + '/' + project.version + '/'
        for object_info in objects['Contents']:
            key = object_info['Key']
            tags = s3.get_object_tagging(Bucket=bucket, Key=key)
            if key.removeprefix(project_prefix) in alter_paths:
                self.assertEqual(tags['TagSet'], [], key)
            else:
                self.assertEqual(tags['TagSet'], custom_tagset, key)

    def test_upload_controlled_projects(self):
        """
        Test uploading controlled-access projects to S3.
        """
        create_s3_server_access_log_bucket()

        project1 = PublishedProject.objects.get(slug='demoeicu',
                                                version='2.0.0')

        self.assertFalse(check_s3_bucket_exists(project1))

        upload_project_to_S3(project1)

        self.assertTrue(check_s3_bucket_exists(project1))

        # FIXME: upload_project_to_S3 does not set an explicit
        # PublicAccessBlockConfiguration for the controlled bucket.
        # self.assert_bucket_is_not_public(get_bucket_name(project1))

        self.assert_project_files_uploaded([project1])

    def assert_project_files_uploaded(self, projects):
        """
        Check that the given projects' files were uploaded.
        """
        s3 = create_s3_client()
        expected_files = {}
        bucket = get_bucket_name(projects[0])
        for project in projects:
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

    def test_controlled_access_points(self):
        """
        Test creation of S3 access points.
        """
        create_s3_server_access_log_bucket()

        project = PublishedProject.objects.get(slug='demoeicu',
                                               version='2.0.0')

        # Create some example users.

        existing_aws_users = self.create_example_users(
            project=project,
            count=999,
            aws_verified=True,
            signed_dua=True,
        )
        existing_nonaws_users = self.create_example_users(
            project=project,
            count=50,
            aws_verified=False,
            signed_dua=True,
        )
        add_aws_users = self.create_example_users(
            project=project,
            count=5,
            aws_verified=True,
            signed_dua=False,
        )
        add_nonaws_users = self.create_example_users(
            project=project,
            count=5,
            aws_verified=False,
            signed_dua=False,
        )

        for user in [existing_nonaws_users[0], existing_aws_users[0]]:
            self.assertTrue(can_view_project_files(project, user))
        for user in [add_nonaws_users[0], add_aws_users[0]]:
            self.assertFalse(can_view_project_files(project, user))

        # Upload the project to S3 and create initial access points.

        aws = AWS.objects.create(
            project=project,
            bucket_name=get_bucket_name(project),
            is_private=True,
        )
        upload_project_to_S3(project)
        aws.sent_files = True
        aws.save()

        # Existing users should have access immediately.

        self.assert_project_users_authorized(project, existing_aws_users)
        self.assertEqual(aws.access_points.count(), 2)

        # As new users sign the DUA, they should be granted access.

        for user in add_aws_users + add_nonaws_users:
            self.client.force_login(user)
            initials = DUASignature.get_user_initials(user)
            self.client.post(
                reverse('sign_dua', args=(project.slug, project.version)),
                data={'agree': '', 'initials': initials},
            )
            self.assertTrue(can_view_project_files(project, user))

            if user in add_aws_users:
                existing_aws_users.append(user)
            self.assert_project_users_authorized(project, existing_aws_users)

        self.assertEqual(aws.access_points.count(), 3)

    def assert_project_users_authorized(self, project, users):
        """
        Check that the given users can access the project via S3.
        """
        s3control = create_s3_control_client()

        all_expected_users = set(user.username for user in users)
        all_authorized_users = set()

        principal_re = re.compile(r'"(AIDA[A-Z0-9]+)"')
        for access_point in project.aws.access_points.all():
            # Retrieve the policy for this access point.  Note that
            # here, the behavior of moto differs drastically from AWS:
            # moto returns the same JSON document we uploaded, whereas
            # AWS returns a preprocessed version.  In particular, AWS
            # converts valid userids into ARNs, which we're assuming
            # is *not* done here!

            response = s3control.get_access_point_policy(
                AccountId=settings.AWS_ACCOUNT_ID,
                Name=access_point.name,
            )
            policy = response['Policy']

            # Find userids that are listed in the policy.
            # These should match the list of users for this access point.

            authorized_userids = set()
            for m in principal_re.finditer(policy):
                authorized_userids.add(m.group(1))

            expected_userids = set()
            for user in access_point.users.all():
                if user.cloud_information.aws_verification_datetime:
                    expected_userids.add(user.cloud_information.aws_userid)
                    all_authorized_users.add(user.username)

            self.assertSetEqual(authorized_userids, expected_userids)

        self.assertSetEqual(all_authorized_users, all_expected_users)

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

    def create_example_users(self, project, count, aws_verified, signed_dua):
        """
        Create example users for testing a project.

        Each of the generated users will have completed the training
        requirements for the given project.  If aws_verified is true,
        the user will also have a verified AWS identity; if signed_dua
        is true, the user will have signed the project DUA.
        """
        training_types = list(project.required_trainings.all())
        users = []
        now = timezone.now()
        for _ in range(count):
            n = self.user_counter
            self.user_counter += 1

            user = User.objects.create(
                username=f"s3test{n}",
                email=f"s3test{n}@example.org",
                is_active=True,
                is_credentialed=True,
                credential_datetime=now,
            )
            Profile.objects.create(
                user=user,
                first_names=f"Test{n}",
                last_name=f"User{n}",
            )
            users.append(user)
            for i, training_type in enumerate(training_types):
                Training.objects.create(
                    user=user,
                    slug=f"s3test{n}tr{i}",
                    training_type=training_type,
                    status=TrainingStatus.ACCEPTED,
                    process_datetime=now,
                )
            if aws_verified:
                CloudInformation.objects.create(
                    user=user,
                    aws_id=f"{n:012d}",
                    aws_userid=f"AIDA{n:017X}",
                    aws_user_arn=f"arn:aws:iam::{n:012d}:user/somebody",
                    aws_verification_datetime=now,
                )
            if signed_dua:
                user.dua_signatures.create(project=project)

        return users

    def test_disable_project_access(self):
        """
        Test that disabling access deletes access points from S3 and
        sets access_disabled=True without deleting project files.
        """
        create_s3_server_access_log_bucket()

        project = PublishedProject.objects.get(slug='demoeicu', version='2.0.0')

        # Create users and upload project
        _ = self.create_example_users(
            project=project, count=5, aws_verified=True, signed_dua=True
        )
        aws = AWS.objects.create(
            project=project,
            bucket_name=get_bucket_name(project),
            is_private=True,
        )
        upload_project_to_S3(project)
        aws.sent_files = True
        aws.save()

        self.assertGreater(aws.access_points.count(), 0)
        self.assertFalse(aws.access_disabled)

        # Disable access
        disable_project_access_in_s3(project)

        aws.refresh_from_db()
        self.assertEqual(aws.access_points.count(), 0)
        self.assertTrue(aws.access_disabled)

        # Files should still exist in S3
        self.assertTrue(check_s3_bucket_exists(project))
        self.assert_project_files_uploaded([project])

    def test_restore_project_access(self):
        """
        Test that restoring access recreates access points and clears access_disabled.
        """
        create_s3_server_access_log_bucket()

        project = PublishedProject.objects.get(slug='demoeicu', version='2.0.0')

        users = self.create_example_users(
            project=project, count=5, aws_verified=True, signed_dua=True
        )
        aws = AWS.objects.create(
            project=project,
            bucket_name=get_bucket_name(project),
            is_private=True,
        )
        upload_project_to_S3(project)
        aws.sent_files = True
        aws.save()

        # Disable then restore
        disable_project_access_in_s3(project)

        aws.refresh_from_db()
        self.assertTrue(aws.access_disabled)
        self.assertEqual(aws.access_points.count(), 0)

        restore_project_access_in_s3(project)

        aws.refresh_from_db()
        self.assertFalse(aws.access_disabled)
        self.assertGreater(aws.access_points.count(), 0)
        self.assert_project_users_authorized(project, users)

    def test_disable_access_blocks_enable_aws_access(self):
        """
        Test that a user cannot enable AWS access when access_disabled=True.
        """
        create_s3_server_access_log_bucket()

        project = PublishedProject.objects.get(slug='demoeicu', version='2.0.0')

        users = self.create_example_users(
            project=project, count=2, aws_verified=True, signed_dua=True
        )
        aws = AWS.objects.create(
            project=project,
            bucket_name=get_bucket_name(project),
            is_private=True,
        )
        upload_project_to_S3(project)
        aws.sent_files = True
        aws.save()

        disable_project_access_in_s3(project)

        # User tries to enable AWS access — should be blocked
        user = users[0]
        self.client.force_login(user)
        self.client.post(
            reverse('enable_aws_access', args=(project.slug, project.version))
        )

        aws.refresh_from_db()
        # Access points should still be empty
        self.assertEqual(aws.access_points.count(), 0)
        self.assertTrue(aws.access_disabled)
