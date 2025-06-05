import os
import tempfile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from project.models import PublishedProject, DUASignature, AccessPolicy
from user.models import User


class ProjectSHA256SumsTests(TestCase):
    """Test suite for the SHA256SUMS endpoint"""

    def setUp(self):
        # Create users
        self.user = User.objects.create(username='testuser',
                                        email='test@example.com',
                                        password='testpass123')
        self.unauthorized_user = User.objects.create(username='unauthorized',
                                                     email='unauthorized@example.com',
                                                     password='testpass123')
        self.rgmark = User.objects.create(username='rgmark',
                                          email='rgmark@mit.edu',
                                          password='Tester11!',
                                          is_credentialed=True)
        # Create project
        self.project = PublishedProject.objects.create(
            slug='demoeicu',
            version='2.0.0',
            title='Demo eICU Collaborative Research Database',
            resource_type=0,
            publish_datetime='2024-01-01T00:00:00Z',
            access_policy=AccessPolicy.CREDENTIALED
        )
        # File setup
        self.temp_dir = tempfile.mkdtemp()
        self.project.file_root = lambda: self.temp_dir
        self.sha256sums_path = os.path.join(self.temp_dir, 'SHA256SUMS.txt')
        with open(self.sha256sums_path, 'w') as f:
            f.write('test content')
        self.client = APIClient()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            for file in os.listdir(self.temp_dir):
                os.remove(os.path.join(self.temp_dir, file))
            os.rmdir(self.temp_dir)

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
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()['error'], 'SHA256SUMS.txt not found for this project')

    def test_successful_download(self):
        url = reverse('published_project_sha256sums',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version})
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="SHA256SUMS.txt"')
        self.assertEqual(response.content.decode(), 'test content')

    def test_nonexistent_project(self):
        url = reverse('published_project_sha256sums',
                      kwargs={'project_slug': 'nonexistent',
                              'version': '1.0.0'})
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rgmark_dua_signing(self):
        url = reverse('published_project_sha256sums',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version})
        self.client.force_authenticate(user=self.rgmark)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        DUASignature.objects.create(user=self.rgmark, project=self.project)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="SHA256SUMS.txt"')
        self.assertEqual(response.content.decode(), 'test content')
