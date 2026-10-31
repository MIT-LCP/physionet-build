"""Embargoes must protect direct file URLs as well as project pages."""

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from project.authorization.access import can_access_project, can_view_project_files
from project.cloud.s3 import public_s3_download_url, upload_list_of_projects, upload_project_to_S3
from project.models import AccessPolicy, AWS, CoreProject, DUASignature, PublishedProject, ProjectType
from user.models import User


class EmbargoDownloadTests(TestCase):
    def setUp(self):
        kind = ProjectType.objects.create(id=123, name='Embargo Test')
        self.project = PublishedProject.objects.create(
            core_project=CoreProject.objects.create(), resource_type=kind,
            slug='embargo-test', submission_slug='embargo-test', version='1.0',
            title='Embargo Test', access_policy=AccessPolicy.OPEN,
            embargo_files_days=30,
        )
        self.files = tempfile.TemporaryDirectory()
        self.addCleanup(self.files.cleanup)
        self.file_root = Path(self.files.name)
        (self.file_root / 'data.txt').write_text('embargoed data')
        self.zip_path = self.file_root / 'archive.zip'
        self.zip_path.write_bytes(b'embargoed zip')
        for name, path in (('file_root', self.file_root), ('zip_name', self.zip_path)):
            patcher = mock.patch.object(PublishedProject, name, return_value=str(path))
            patcher.start()
            self.addCleanup(patcher.stop)

    def file_url(self):
        return reverse('serve_published_project_file', args=(self.project.slug, self.project.version, 'data.txt'))

    def zip_url(self):
        return reverse('serve_published_project_zip', args=(self.project.slug, self.project.version))

    def test_open_files_and_zip_are_blocked_during_embargo(self):
        self.assertTrue(self.project.embargo_active())
        self.assertFalse(can_access_project(self.project, AnonymousUser()))
        for url in (self.file_url(), self.zip_url()):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        display_url = reverse('display_published_project_file', args=(
            self.project.slug, self.project.version, 'data.txt',
        ))
        panel_url = reverse('published_files_panel', args=(self.project.slug, self.project.version))
        self.assertEqual(self.client.get(display_url).status_code, 403)
        self.assertEqual(self.client.get(panel_url, {'subdir': ''}).status_code, 404)

    def test_existing_dua_does_not_override_embargo(self):
        user = User.objects.create_user(
            email='embargo@example.com', username='embargouser',
            password='test-password', is_active=True,
        )
        user.is_credentialed = True
        user.save(update_fields=['is_credentialed'])
        self.project.access_policy = AccessPolicy.CREDENTIALED
        self.project.save(update_fields=['access_policy'])
        DUASignature.objects.create(project=self.project, user=user)
        self.client.force_login(user)
        self.assertFalse(can_access_project(self.project, user))
        self.assertFalse(can_view_project_files(self.project, user))
        self.assertEqual(self.client.get(self.file_url()).status_code, 403)
        project_url = reverse('published_project', args=(self.project.slug, self.project.version))
        aws_url = reverse('enable_aws_access', args=(self.project.slug, self.project.version))
        cloud_url = reverse('published_project_request_access', args=(
            self.project.slug, self.project.version, 2,
        ))
        for url in (aws_url, cloud_url):
            self.assertRedirects(self.client.get(url), project_url, fetch_redirect_response=False)

    def test_signed_anonymous_cookie_does_not_override_embargo(self):
        cookie_response = HttpResponse()
        cookie_response.set_signed_cookie('anonymousaccess', 'secret-link')
        self.client.cookies['anonymousaccess'] = cookie_response.cookies['anonymousaccess'].value
        with mock.patch.object(PublishedProject, 'get_anonymous_url', return_value='secret-link'):
            for url in (self.file_url(), self.zip_url()):
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_lightwave_hides_embargoed_project_and_denies_its_files(self):
        self.project.has_wfdb = True
        self.project.save(update_fields=['has_wfdb'])
        url = reverse('lightwave_server')
        with mock.patch('lightwave.views.serve_lightwave', return_value=HttpResponse()) as serve:
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(serve.call_args.kwargs['dblist'], '')
        response = self.client.get(url, {'db': 'embargo-test/1.0/data.txt'})
        self.assertEqual(response.json()['code'], 'FORBIDDEN')

    def test_access_returns_after_embargo_expires(self):
        PublishedProject.objects.filter(pk=self.project.pk).update(
            publish_datetime=timezone.now() - timedelta(days=31)
        )
        self.project.refresh_from_db()
        self.assertFalse(self.project.embargo_active())
        self.assertTrue(can_access_project(self.project, AnonymousUser()))
        self.assertEqual(self.client.get(self.file_url()).status_code, 200)

    def test_signed_cookie_still_allows_access_without_embargo(self):
        self.project.embargo_files_days = None
        self.project.access_policy = AccessPolicy.CREDENTIALED
        self.project.save(update_fields=['embargo_files_days', 'access_policy'])
        cookie_response = HttpResponse()
        cookie_response.set_signed_cookie('anonymousaccess', 'secret-link')
        self.client.cookies['anonymousaccess'] = cookie_response.cookies['anonymousaccess'].value
        with mock.patch.object(PublishedProject, 'get_anonymous_url', return_value='secret-link'):
            self.assertEqual(self.client.get(self.file_url()).status_code, 200)

    @override_settings(REDIRECT_DOWNLOADS_TO_CLOUD=True)
    def test_embargo_does_not_offer_public_s3_url(self):
        AWS.objects.create(
            project=self.project, bucket_name='physionet-open',
            is_private=False, sent_files=True,
        )
        self.assertIsNone(public_s3_download_url(self.project, 'data.txt'))

    @override_settings(AWS_PROFILE='default', S3_OPEN_ACCESS_BUCKET='physionet-open')
    def test_embargoed_project_is_not_uploaded_to_s3(self):
        with mock.patch('project.cloud.s3.create_s3_client', return_value=None) as create_client:
            with self.assertRaisesRegex(ValueError, 'embargo'):
                upload_project_to_S3(self.project)
        create_client.assert_not_called()

    def test_bulk_s3_upload_skips_embargoed_project(self):
        ready = mock.Mock()
        ready.embargo_active.return_value = False
        with mock.patch('project.cloud.s3.upload_project_to_S3') as upload:
            upload_list_of_projects([self.project, ready])
        upload.assert_called_once_with(ready)
