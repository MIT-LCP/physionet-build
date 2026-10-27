"""
Tests for the OAuth state check in the ORCID linking and login flows.
"""
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from user import views
from user.models import Orcid

User = get_user_model()

ORCID_SETTINGS = {
    'ORCID_CLIENT_ID': 'APP-TEST',
    'ORCID_CLIENT_SECRET': 'test-secret',
    'ORCID_REDIRECT_URI': 'http://testserver/authorcid/',
    'ORCID_LOGIN_REDIRECT_URI': 'http://testserver/authorcid_login/',
    'ORCID_SCOPE': '/read-limited',
    'ORCID_AUTH_URL': 'https://sandbox.orcid.org/oauth/authorize',
    'ORCID_TOKEN_URL': 'https://sandbox.orcid.org/oauth/token',
}

ORCID_TOKEN = {
    'orcid': '0000-0002-1825-0097',
    'name': 'Test User',
    'access_token': 'c4548597-e368-4acb-bd06-1d8bcf13de46',
    'refresh_token': '3c68e7a9-7418-4d8d-bf31-1afcd2b7c742',
    'token_type': 'bearer',
    'scope': '/read-limited',
    'expires_at': 2242899965.166591,
}


@override_settings(**ORCID_SETTINGS)
class OrcidLinkStateTests(TestCase):
    """The ORCID link callback only accepts a code with the state it issued."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='orcidtest', email='orcidtest@example.com', password='testpass123',
        )
        self.user.is_active = True
        self.user.save()
        self.client.force_login(self.user)

    def start_link(self):
        response = self.client.post(reverse('edit_orcid'), {'request_orcid': '1'})
        self.assertEqual(response.status_code, 302)
        return parse_qs(urlparse(response.url).query)['state'][0]

    def test_start_link_stores_state(self):
        state = self.start_link()
        self.assertEqual(self.client.session[views.ORCID_LINK_STATE_KEY], state)

    @patch('user.views._fetch_and_validate_token')
    def test_callback_without_session_state_is_rejected(self, mock_fetch):
        response = self.client.get(reverse('auth_orcid'), {'code': 'abc123', 'state': 'anything'})

        self.assertRedirects(response, reverse('edit_orcid'), fetch_redirect_response=False)
        mock_fetch.assert_not_called()
        self.assertFalse(Orcid.objects.filter(user=self.user).exists())

    @patch('user.views._fetch_and_validate_token')
    def test_callback_with_wrong_state_is_rejected(self, mock_fetch):
        self.start_link()
        response = self.client.get(reverse('auth_orcid'), {'code': 'abc123', 'state': 'wrong'})

        self.assertRedirects(response, reverse('edit_orcid'), fetch_redirect_response=False)
        mock_fetch.assert_not_called()
        self.assertFalse(Orcid.objects.filter(user=self.user).exists())
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('Invalid ORCID linking request' in m for m in messages))

    @patch('user.views._fetch_and_validate_token')
    def test_callback_without_state_is_rejected(self, mock_fetch):
        self.start_link()
        response = self.client.get(reverse('auth_orcid'), {'code': 'abc123'})

        self.assertRedirects(response, reverse('edit_orcid'), fetch_redirect_response=False)
        mock_fetch.assert_not_called()

    @patch('user.views._fetch_and_validate_token')
    def test_callback_without_code_is_rejected(self, mock_fetch):
        state = self.start_link()
        response = self.client.get(reverse('auth_orcid'), {'state': state})

        self.assertRedirects(response, reverse('edit_orcid'), fetch_redirect_response=False)
        mock_fetch.assert_not_called()

    @patch('user.views._fetch_and_validate_token')
    def test_callback_with_matching_state_links_account(self, mock_fetch):
        mock_fetch.return_value = (True, dict(ORCID_TOKEN))
        state = self.start_link()
        response = self.client.get(reverse('auth_orcid'), {'code': 'abc123', 'state': state})

        self.assertRedirects(response, reverse('edit_orcid'), fetch_redirect_response=False)
        mock_fetch.assert_called_once()
        self.assertEqual(Orcid.objects.get(user=self.user).orcid_id, ORCID_TOKEN['orcid'])
        self.assertNotIn(views.ORCID_LINK_STATE_KEY, self.client.session)

    @patch('user.views._fetch_and_validate_token')
    def test_state_cannot_be_reused(self, mock_fetch):
        mock_fetch.return_value = (True, dict(ORCID_TOKEN))
        state = self.start_link()
        self.client.get(reverse('auth_orcid'), {'code': 'abc123', 'state': state})
        self.client.get(reverse('auth_orcid'), {'code': 'def456', 'state': state})

        mock_fetch.assert_called_once()


@override_settings(ORCID_LOGIN_ENABLED=True, **ORCID_SETTINGS)
class OrcidLoginStateTests(TestCase):
    """
    The ORCID login URLs are only registered when ORCID_LOGIN_ENABLED is set
    at startup, so these tests call the views directly.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def make_request(self, path, params=None, session=None):
        request = self.factory.get(path, params or {})
        SessionMiddleware(lambda r: None).process_request(request)
        for key, value in (session or {}).items():
            request.session[key] = value
        request.user = AnonymousUser()
        request._messages = FallbackStorage(request)
        return request

    def test_init_login_sends_and_stores_state(self):
        request = self.make_request('/orcid_init_login')
        response = views.orcid_init_login(request)

        self.assertEqual(response.status_code, 302)
        state = parse_qs(urlparse(response.url).query)['state'][0]
        self.assertTrue(state)
        self.assertEqual(request.session[views.ORCID_LOGIN_STATE_KEY], state)

    @patch('user.views._fetch_and_validate_token')
    def test_login_callback_with_wrong_state_is_rejected(self, mock_fetch):
        request = self.make_request(
            '/authorcid_login/', {'code': 'abc123', 'state': 'wrong'},
            session={views.ORCID_LOGIN_STATE_KEY: 'expected'},
        )
        response = views.auth_orcid_login(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))
        mock_fetch.assert_not_called()

    @patch('user.views._fetch_and_validate_token')
    def test_login_callback_without_session_state_is_rejected(self, mock_fetch):
        request = self.make_request('/authorcid_login/', {'code': 'abc123', 'state': 'anything'})
        views.auth_orcid_login(request)

        mock_fetch.assert_not_called()

    @patch('user.views._fetch_and_validate_token')
    def test_login_callback_with_matching_state_exchanges_code(self, mock_fetch):
        mock_fetch.return_value = (False, None)
        request = self.make_request(
            '/authorcid_login/', {'code': 'abc123', 'state': 'expected'},
            session={views.ORCID_LOGIN_STATE_KEY: 'expected'},
        )
        views.auth_orcid_login(request)

        mock_fetch.assert_called_once()
        self.assertNotIn(views.ORCID_LOGIN_STATE_KEY, request.session)
