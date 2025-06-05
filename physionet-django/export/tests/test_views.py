from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from project.models import PublishedProject, ProjectType, AccessPolicy


class TestRateLimiting(TestCase):
    """Test rate limiting on API endpoints"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create test project
        self.project = PublishedProject.objects.create(
            slug='test-project',
            version='1.0.0',
            title='Test Project',
            abstract='Test abstract',
            access_policy=AccessPolicy.CREDENTIALED
        )

        # Create test resource type
        self.resource_type = ProjectType.objects.create(
            name='TestType'
        )

    def test_anonymous_rate_limit(self):
        """Test rate limiting for anonymous users"""
        url = reverse('published_project_list')

        # Make requests up to the limit
        for _ in range(20):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Next request should be rate limited
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_authenticated_rate_limit(self):
        """Test rate limiting for authenticated users"""
        url = reverse('published_project_list')

        # Create and authenticate test user
        self.client.force_authenticate(user=self.project.authors.first())

        # Make requests up to the limit
        for _ in range(100):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Next request should be rate limited
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_search_rate_limit(self):
        """Test rate limiting on search endpoint"""
        url = reverse('published_project_search')

        # Make requests up to the limit
        for _ in range(20):
            response = self.client.get(url, {'search_term': 'test'})
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Next request should be rate limited
        response = self.client.get(url, {'search_term': 'test'})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_project_detail_rate_limit(self):
        """Test rate limiting on project detail endpoint"""
        url = reverse('published_project_detail',
                      kwargs={'project_slug': 'test-project', 'version': '1.0.0'})

        # Make requests up to the limit
        for _ in range(20):
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Next request should be rate limited
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
