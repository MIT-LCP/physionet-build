import os
import shutil
import tempfile
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from project.models import CoreProject, PublishedProject, DUASignature, AccessPolicy, ProjectType
from user.models import User


class ProjectSHA256SumsTests(TestCase):
    """Test suite for the SHA256SUMS endpoint"""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(username='sha256user',
                                             email='sha256-user@example.com',
                                             password='testpass123')
        self.unauthorized_user = User.objects.create_user(username='sha256unauthorized',
                                                          email='sha256-unauthorized@example.com',
                                                          password='testpass123')
        self.credentialed_user = User.objects.create_user(username='sha256credentialed',
                                                          email='sha256-credentialed@example.com',
                                                          password='testpass123')
        self.credentialed_user.is_credentialed = True
        self.credentialed_user.save(update_fields=['is_credentialed'])

        self.project = PublishedProject.objects.create(
            slug='sha256-test',
            submission_slug='sha256-test',
            version='2.0.0',
            title='SHA256SUMS Test Database',
            resource_type=ProjectType.objects.create(id=124, name='SHA256SUMS Test Type'),
            core_project=CoreProject.objects.create(),
            publish_datetime='2024-01-01T00:00:00Z',
            access_policy=AccessPolicy.CREDENTIALED
        )

        # The view loads its own copy of the project, so patch the class
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        patcher = mock.patch.object(PublishedProject, 'file_root', return_value=self.temp_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sha256sums_path = os.path.join(self.temp_dir, 'SHA256SUMS.txt')
        with open(self.sha256sums_path, 'w') as f:
            f.write('test content')
        self.client = APIClient()

    def test_unauthorized_access(self):
        url = reverse('published_project_sha256sums',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(user=self.unauthorized_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_file(self):
        os.remove(self.sha256sums_path)
        url = reverse('published_project_sha256sums',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version})
        DUASignature.objects.create(user=self.credentialed_user, project=self.project)
        self.client.force_authenticate(user=self.credentialed_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()['error'], 'SHA256SUMS.txt not found for this project')

    def test_successful_download(self):
        url = reverse('published_project_sha256sums',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version})
        DUASignature.objects.create(user=self.credentialed_user, project=self.project)
        self.client.force_authenticate(user=self.credentialed_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="SHA256SUMS.txt"')
        self.assertEqual(b''.join(response.streaming_content).decode(), 'test content')

    def test_nonexistent_project(self):
        url = reverse('published_project_sha256sums',
                      kwargs={'project_slug': 'nonexistent',
                              'version': '1.0.0'})
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_dua_signature_grants_access(self):
        url = reverse('published_project_sha256sums',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version})
        self.client.force_authenticate(user=self.credentialed_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        DUASignature.objects.create(user=self.credentialed_user, project=self.project)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="SHA256SUMS.txt"')
        self.assertEqual(b''.join(response.streaming_content).decode(), 'test content')
