from django.test import TestCase, override_settings
from unittest.mock import patch, MagicMock
from search.models import FederatedSite
from search.federated_search import FederatedSearchService
from search.adapters import PhysioNetAdapter, get_adapter


class FederatedSiteModelTest(TestCase):
    def test_create_federated_site(self):
        """Test creating a federated site"""
        site = FederatedSite.objects.create(
            name='testsite',
            display_name='Test Site',
            base_url='https://example.com',
            enabled=True
        )
        self.assertEqual(site.name, 'testsite')
        self.assertTrue(site.enabled)
        self.assertEqual(str(site), 'Test Site (testsite)')

    def test_get_full_search_url(self):
        """Test URL construction"""
        site = FederatedSite.objects.create(
            name='testsite',
            display_name='Test Site',
            base_url='https://example.com',
            api_endpoint='/api/v1/projects/published/search/',
            enabled=True
        )
        expected_url = 'https://example.com/api/v1/projects/published/search/'
        self.assertEqual(site.get_full_search_url(), expected_url)

    def test_ssrf_protection_localhost(self):
        """Test that localhost is blocked"""
        from django.core.exceptions import ValidationError

        site = FederatedSite(
            name='badsite',
            display_name='Bad Site',
            base_url='http://localhost:8000',
        )
        with self.assertRaises(ValidationError):
            site.clean()

    def test_ssrf_protection_private_ip(self):
        """Test that private IPs are blocked"""
        from django.core.exceptions import ValidationError

        private_ips = [
            'http://127.0.0.1',
            'http://192.168.1.1',
            'http://10.0.0.1',
            'http://172.16.0.1',
        ]

        for ip in private_ips:
            site = FederatedSite(
                name='badsite',
                display_name='Bad Site',
                base_url=ip,
            )
            with self.assertRaises(ValidationError):
                site.clean()


class FederatedSearchServiceTest(TestCase):
    def setUp(self):
        self.site = FederatedSite.objects.create(
            name='testsite',
            display_name='Test Site',
            base_url='https://example.com',
            enabled=True
        )

    def test_is_enabled_with_active_sites(self):
        """Test that service is enabled when sites exist"""
        self.assertTrue(FederatedSearchService.is_enabled())

    def test_is_enabled_no_sites(self):
        """Test that service is disabled when no sites in DB"""
        FederatedSite.objects.all().delete()
        self.assertFalse(FederatedSearchService.is_enabled())

    @patch('search.adapters.requests.get')
    def test_successful_search(self, mock_get):
        """Test successful federated search"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'results': [{
                'title': 'Test Project',
                'slug': 'test',
                'version': '1.0.0',
                'abstract': 'Test abstract',
                'short_description': 'Test description',
                'publish_date': '2024-01-01',
                'resource_type': 0,
                'access_policy': 0,
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        results = FederatedSearchService.search('test')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Test Project')
        self.assertTrue(results[0]['is_federated'])
        self.assertEqual(results[0]['source_site_name'], 'testsite')

    @patch('search.adapters.requests.get')
    def test_timeout_handling(self, mock_get):
        """Test that timeouts are handled silently"""
        import requests
        mock_get.side_effect = requests.Timeout()

        results = FederatedSearchService.search('test')

        # Should return empty list, not raise exception
        self.assertEqual(results, [])

    @patch('search.adapters.requests.get')
    def test_connection_error_handling(self, mock_get):
        """Test that connection errors are handled silently"""
        import requests
        mock_get.side_effect = requests.ConnectionError()

        results = FederatedSearchService.search('test')

        # Should return empty list, not raise exception
        self.assertEqual(results, [])

    @patch('search.adapters.requests.get')
    def test_multiple_sites_search(self, mock_get):
        """Test searching across multiple sites"""
        # Create second site
        site2 = FederatedSite.objects.create(
            name='testsite2',
            display_name='Test Site 2',
            base_url='https://example2.com',
            enabled=True
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'results': [{
                'title': 'Test Project',
                'slug': 'test',
                'version': '1.0.0',
                'abstract': 'Test abstract',
                'publish_date': '2024-01-01',
                'resource_type': 0,
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        results = FederatedSearchService.search('test')

        # Should get results from both sites
        self.assertEqual(len(results), 2)


class PhysioNetAdapterTest(TestCase):
    def setUp(self):
        self.site = FederatedSite.objects.create(
            name='testsite',
            display_name='Test Site',
            base_url='https://example.com',
            enabled=True
        )
        self.adapter = PhysioNetAdapter(self.site)

    def test_normalize_result(self):
        """Test result normalization"""
        raw = {
            'title': 'Test',
            'slug': 'test',
            'version': '1.0.0',
            'abstract': 'Abstract',
            'short_description': 'Short desc',
            'publish_date': '2024-01-01',
            'resource_type': 0,
        }

        normalized = self.adapter.normalize_result(raw)

        self.assertEqual(normalized['title'], 'Test')
        self.assertTrue(normalized['is_federated'])
        self.assertEqual(normalized['source_site_name'], 'testsite')
        self.assertEqual(normalized['source_site_display_name'], 'Test Site')
        self.assertIn('/content/test/1.0.0/', normalized['external_url'])

    @patch('search.adapters.requests.get')
    def test_search_with_auth_token(self, mock_get):
        """Test that auth token is included in headers"""
        self.site.auth_token = 'test_token_123'
        self.site.save()

        mock_response = MagicMock()
        mock_response.json.return_value = {'results': []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        adapter = PhysioNetAdapter(self.site)
        adapter.search('test', ['all'])

        # Verify auth header was set
        call_kwargs = mock_get.call_args[1]
        self.assertIn('Authorization', call_kwargs['headers'])
        self.assertEqual(call_kwargs['headers']['Authorization'], 'Bearer test_token_123')

    def test_get_adapter_factory(self):
        """Test adapter factory"""
        adapter = get_adapter(self.site)
        self.assertIsInstance(adapter, PhysioNetAdapter)