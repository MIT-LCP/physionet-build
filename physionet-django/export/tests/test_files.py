import os
import tempfile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from project.models import PublishedProject, DUASignature, AccessPolicy, ProjectType, CoreProject
from user.models import User
from oauth2_provider.models import get_application_model, Application, AccessToken
from django.utils import timezone
from datetime import timedelta
import time
from project.projectfiles.local import LocalProjectFiles


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
            resource_type=ProjectType.objects.get(id=0),
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


class ProjectFileDownloadTests(TestCase):
    """Test suite for the file download endpoint"""

    def setUp(self):
        # Create users with unique usernames
        timestamp = int(time.time())
        self.user = User.objects.create(username=f'testuser_{timestamp}',
                                        email=f'test_{timestamp}@example.com',
                                        password='testpass123',
                                        is_credentialed=True)
        self.unauthorized_user = User.objects.create(username=f'unauthorized_{timestamp}',
                                                     email=f'unauthorized_{timestamp}@example.com',
                                                     password='testpass123')
        self.rgmark = User.objects.create(username=f'rgmark_{timestamp}',
                                          email=f'rgmark_{timestamp}@mit.edu',
                                          password='Tester11!',
                                          is_credentialed=True)
        # Create core project
        self.core_project = CoreProject.objects.create()
        # Create project with unique slug
        self.project = PublishedProject.objects.create(
            slug=f'demoeicu_{timestamp}',
            version='2.0.0',
            title='Demo eICU Collaborative Research Database',
            resource_type=ProjectType.objects.get(id=0),  # Database type
            publish_datetime='2024-01-01T00:00:00Z',
            access_policy=AccessPolicy.CREDENTIALED,
            core_project=self.core_project,
            allow_file_downloads=True
        )
        # Set up files attribute
        self.project.files = LocalProjectFiles()
        # Create project file root directory
        os.makedirs(self.project.file_root(), exist_ok=True)
        # Create test file in the project's file root
        self.test_file_path = os.path.join(self.project.file_root(), 'test.txt')
        with open(self.test_file_path, 'w') as f:
            f.write('test content')
        self.client = APIClient()

        # Create OAuth application and token
        self.application = Application.objects.create(
            name=f"Test Application {timestamp}",
            redirect_uris="http://localhost",
            user=self.user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret="testsecret",
        )
        self.access_token = AccessToken.objects.create(
            user=self.user,
            application=self.application,
            token=f"test-token-{timestamp}",
            expires=timezone.now() + timedelta(days=1),
            scope="data:download",
        )

        # Sign DUA for the user
        DUASignature.objects.create(user=self.user, project=self.project)

    def tearDown(self):
        if os.path.exists(self.project.file_root()):
            for file in os.listdir(self.project.file_root()):
                os.remove(os.path.join(self.project.file_root(), file))
            os.rmdir(self.project.file_root())

    def test_unauthorized_access(self):
        url = reverse('published_project_file_download',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version,
                              'filepath': 'test.txt'})
        # No token
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()['error'], 'Invalid or missing token')

        # Invalid token
        response = self.client.get(url, HTTP_AUTHORIZATION='Bearer invalid-token')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()['error'], 'Invalid or missing token')

        # Token without required scope
        AccessToken.objects.create(
            user=self.user,
            application=self.application,
            token="test-token-no-scope",
            expires=timezone.now() + timedelta(days=1),
            scope="profile:read",
        )
        response = self.client.get(url, HTTP_AUTHORIZATION='Bearer test-token-no-scope')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()['error'], 'Invalid or missing token')

    def test_missing_file(self):
        url = reverse('published_project_file_download',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version,
                              'filepath': 'nonexistent.txt'})
        response = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.access_token.token}')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()['error'], 'File not found')

    def test_successful_download(self):
        url = reverse('published_project_file_download',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version,
                              'filepath': 'test.txt'})
        response = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.access_token.token}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="test.txt"')
        # Read the streaming content
        content = b''.join(response.streaming_content)
        self.assertEqual(content.decode(), 'test content')

    def test_nonexistent_project(self):
        url = reverse('published_project_file_download',
                      kwargs={'project_slug': 'nonexistent',
                              'version': '1.0.0',
                              'filepath': 'test.txt'})
        response = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.access_token.token}')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rgmark_dua_signing(self):
        url = reverse('published_project_file_download',
                      kwargs={'project_slug': self.project.slug,
                              'version': self.project.version,
                              'filepath': 'test.txt'})
        # Create token for rgmark
        AccessToken.objects.create(
            user=self.rgmark,
            application=self.application,
            token="test-token-rgmark",
            expires=timezone.now() + timedelta(days=1),
            scope="data:download",
        )
        # Try to access without DUA
        response = self.client.get(url, HTTP_AUTHORIZATION='Bearer test-token-rgmark')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()['error'], 'You do not have permission to access this project')

        # Sign DUA and try again
        DUASignature.objects.create(user=self.rgmark, project=self.project)
        response = self.client.get(url, HTTP_AUTHORIZATION='Bearer test-token-rgmark')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="test.txt"')
        # Read the streaming content
        content = b''.join(response.streaming_content)
        self.assertEqual(content.decode(), 'test content')
