"""
Tests for ORCID account linking, login, sign-up and activation, and the User
ORCID helpers, including the OAuth state check.
"""
import importlib.util
import re
from unittest import skipIf
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import NoReverseMatch, resolve, reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError

from physionet.urls import urlpatterns as root_urlpatterns
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

OTHER_ORCID_ID = '0000-0001-5109-3700'
NEW_ACCESS_TOKEN = 'a1b2c3d4-e5f6-a7b8-c9d0-e1f2a3b4c5d6'

# With ORCID_LOGIN_ENABLED on, the view also requires a signed id_token (ORCID sends one for the openid scope).
LOGIN_TOKEN = dict(ORCID_TOKEN, id_token='test-id-token')

ORCID_LOGIN_URL_NAMES = {'auth_orcid_login', 'orcid_init_login', 'orcid_register', 'orcid_activate_user'}


def orcid_login_urlpatterns():
    """
    Return the ORCID login routes from user/urls.py. That file only adds them
    when ORCID_LOGIN_ENABLED is set at startup, so run it again with the
    setting on, as a separate module (the imported user.urls is unchanged).
    """
    with override_settings(ORCID_LOGIN_ENABLED=True):
        spec = importlib.util.find_spec('user.urls')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    patterns = [p for p in module.urlpatterns if getattr(p, 'name', None) in ORCID_LOGIN_URL_NAMES]
    if len(patterns) != len(ORCID_LOGIN_URL_NAMES):
        raise RuntimeError('The ORCID login routes in user/urls.py have changed')
    return patterns


# URL configuration for OrcidLoginTests: the ORCID login routes plus the site's own.
urlpatterns = orcid_login_urlpatterns() + root_urlpatterns


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


@override_settings(ORCID_LOGIN_ENABLED=False, ORCID_DOMAIN='https://sandbox.orcid.org', **ORCID_SETTINGS)
class OrcidLinkTests(TestCase):
    """Linking and unlinking an ORCID account from the user's settings page."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='orcidlink', email='orcidlink@example.com', password='testpass123',
        )
        self.user.is_active = True
        self.user.save()
        self.client.force_login(self.user)

    def start_link(self):
        response = self.client.post(reverse('edit_orcid'), {'request_orcid': '1'})
        self.assertEqual(response.status_code, 302)
        return parse_qs(urlparse(response.url).query)['state'][0]

    def link(self, token):
        """
        Run the link flow with ORCID's token endpoint mocked to return `token`,
        so the view's own token validation still runs.
        """
        state = self.start_link()
        with patch('user.views.OAuth2Session.fetch_token', return_value=dict(token)) as mock_fetch_token:
            response = self.client.get(reverse('auth_orcid'), {'code': 'abc123', 'state': state})
        mock_fetch_token.assert_called_once()
        return response

    def create_other_user_link(self):
        other = User.objects.create_user(
            username='orcidother', email='orcidother@example.com', password='testpass123',
        )
        return Orcid.objects.create(
            user=other, orcid_id=ORCID_TOKEN['orcid'], name='Other User', access_token=NEW_ACCESS_TOKEN,
        )

    def assert_link_refused(self, response):
        self.assertRedirects(response, reverse('edit_orcid'), fetch_redirect_response=False)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ['This ORCID account is already in use by another account!'])

    def test_settings_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('edit_orcid'))

        self.assertRedirects(
            response, f"{settings.LOGIN_URL}?next={reverse('edit_orcid')}", fetch_redirect_response=False,
        )

    def test_settings_page_without_link(self):
        response = self.client.get(reverse('edit_orcid'))

        self.assertContains(response, 'No ORCID iD linked.')
        self.assertContains(response, 'name="request_orcid"')
        self.assertNotContains(response, 'name="remove_orcid"')

    def test_settings_page_with_link(self):
        Orcid.objects.create(user=self.user, orcid_id=ORCID_TOKEN['orcid'])
        response = self.client.get(reverse('edit_orcid'))

        self.assertContains(response, f"{settings.ORCID_DOMAIN}/{ORCID_TOKEN['orcid']}")
        self.assertContains(response, 'name="remove_orcid"')
        self.assertNotContains(response, 'No ORCID iD linked.')
        self.assertNotContains(response, 'name="request_orcid"')

    @patch('user.views.OAuth2Session.fetch_token')
    def test_callback_requires_login(self, mock_fetch_token):
        self.client.logout()
        orcid_count = Orcid.objects.count()
        response = self.client.get(reverse('auth_orcid'), {'code': 'abc123', 'state': 'anything'})

        self.assertEqual(response.status_code, 302)
        url = urlparse(response.url)
        self.assertEqual(url.path, settings.LOGIN_URL)
        self.assertEqual(parse_qs(url.query)['next'], [f"{reverse('auth_orcid')}?code=abc123&state=anything"])
        mock_fetch_token.assert_not_called()
        self.assertEqual(Orcid.objects.count(), orcid_count)

    # Two scopes, so the view's split(',') of ORCID_SCOPE is checked too.
    @override_settings(ORCID_SCOPE='/read-limited,/activities/update')
    def test_link_redirects_to_orcid(self):
        response = self.client.post(reverse('edit_orcid'), {'request_orcid': '1'})

        self.assertEqual(response.status_code, 302)
        url = urlparse(response.url)
        query = parse_qs(url.query)
        self.assertEqual(f'{url.scheme}://{url.netloc}{url.path}', ORCID_SETTINGS['ORCID_AUTH_URL'])
        self.assertEqual(query['response_type'], ['code'])
        self.assertEqual(query['client_id'], [ORCID_SETTINGS['ORCID_CLIENT_ID']])
        self.assertEqual(query['redirect_uri'], [ORCID_SETTINGS['ORCID_REDIRECT_URI']])
        self.assertEqual(query['scope'], ['/read-limited /activities/update'])

    def test_link_saves_id_name_and_tokens(self):
        response = self.link(ORCID_TOKEN)

        self.assertRedirects(response, reverse('edit_orcid'), fetch_redirect_response=False)
        orcid = Orcid.objects.get(user=self.user)
        self.assertEqual(orcid.orcid_id, ORCID_TOKEN['orcid'])
        self.assertEqual(orcid.name, ORCID_TOKEN['name'])
        self.assertEqual(orcid.access_token, ORCID_TOKEN['access_token'])
        self.assertEqual(orcid.refresh_token, ORCID_TOKEN['refresh_token'])
        self.assertEqual(orcid.token_type, ORCID_TOKEN['token_type'])
        self.assertEqual(orcid.token_scope, ORCID_TOKEN['scope'])
        # expires_at is a float; SQLite and PostgreSQL round-trip the DecimalField differently.
        self.assertAlmostEqual(float(orcid.token_expiration), ORCID_TOKEN['expires_at'], places=3)

    def test_link_same_id_again_updates_the_row(self):
        self.link(ORCID_TOKEN)
        first = Orcid.objects.get(user=self.user)

        self.link(dict(ORCID_TOKEN, name='New Name', access_token=NEW_ACCESS_TOKEN))

        orcid = Orcid.objects.get(user=self.user)
        self.assertEqual(orcid.pk, first.pk)
        self.assertEqual(orcid.orcid_id, ORCID_TOKEN['orcid'])
        self.assertEqual(orcid.name, 'New Name')
        self.assertEqual(orcid.access_token, NEW_ACCESS_TOKEN)

    def test_link_different_id_updates_the_row(self):
        self.link(ORCID_TOKEN)
        first = Orcid.objects.get(user=self.user)

        self.link(dict(ORCID_TOKEN, orcid=OTHER_ORCID_ID, access_token=NEW_ACCESS_TOKEN))

        orcid = Orcid.objects.get(user=self.user)
        self.assertEqual(orcid.pk, first.pk)
        self.assertEqual(orcid.orcid_id, OTHER_ORCID_ID)
        self.assertEqual(orcid.access_token, NEW_ACCESS_TOKEN)
        self.assertFalse(Orcid.objects.filter(orcid_id=ORCID_TOKEN['orcid']).exists())

    def test_link_malformed_id_leaves_an_empty_row(self):
        # Records current behavior: for a user with no Orcid row, auth_orcid saves a
        # new row before full_clean(), so a malformed iD raises ValidationError (a
        # server error) and leaves a row with an empty orcid_id. A later change that
        # validates before saving will change this; update the test then.
        with self.assertLogs('django.request', 'ERROR'):
            with self.assertRaises(ValidationError):
                self.link(dict(ORCID_TOKEN, orcid='not-an-orcid-id'))

        orcid = Orcid.objects.get(user=self.user)
        self.assertEqual(orcid.orcid_id, '')
        self.assertEqual(orcid.access_token, '')

    def test_link_id_of_another_user_is_refused(self):
        other_link = self.create_other_user_link()

        response = self.link(ORCID_TOKEN)

        self.assert_link_refused(response)
        self.assertFalse(Orcid.objects.filter(user=self.user).exists())
        other_link.refresh_from_db()
        self.assertEqual(other_link.name, 'Other User')
        self.assertEqual(other_link.access_token, NEW_ACCESS_TOKEN)

    def test_link_id_of_another_user_keeps_own_link(self):
        own_link = Orcid.objects.create(user=self.user, orcid_id=OTHER_ORCID_ID, name='Own Name')
        other_link = self.create_other_user_link()

        response = self.link(ORCID_TOKEN)

        self.assert_link_refused(response)
        own_link.refresh_from_db()
        self.assertEqual(own_link.orcid_id, OTHER_ORCID_ID)
        self.assertEqual(own_link.name, 'Own Name')
        other_link.refresh_from_db()
        self.assertEqual(other_link.name, 'Other User')
        self.assertEqual(other_link.access_token, NEW_ACCESS_TOKEN)

    def test_expired_code_links_nothing(self):
        state = self.start_link()
        with patch('user.views.OAuth2Session.fetch_token', side_effect=InvalidGrantError()) as mock_fetch_token:
            response = self.client.get(reverse('auth_orcid'), {'code': 'abc123', 'state': state})

        mock_fetch_token.assert_called_once()
        self.assertRedirects(response, reverse('edit_orcid'), fetch_redirect_response=False)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ['Invalid Grant Error: authorization code may be expired or invalid.'])
        self.assertFalse(Orcid.objects.filter(user=self.user).exists())

    def test_malformed_access_token_links_nothing(self):
        with self.assertLogs('user.views', 'ERROR'):
            response = self.link(dict(ORCID_TOKEN, access_token='not-a-token'))

        self.assertRedirects(response, reverse('edit_orcid'), fetch_redirect_response=False)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ['Validation Error: ORCID token validation failed.'])
        self.assertFalse(Orcid.objects.filter(user=self.user).exists())

    def test_unlink_deletes_the_row(self):
        Orcid.objects.create(user=self.user, orcid_id=OTHER_ORCID_ID)
        other_link = self.create_other_user_link()

        response = self.client.post(reverse('edit_orcid'), {'remove_orcid': '1'})

        self.assertContains(response, 'No ORCID iD linked.')
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, [])
        self.assertFalse(Orcid.objects.filter(user=self.user).exists())
        self.assertTrue(Orcid.objects.filter(pk=other_link.pk).exists())

    def test_unlink_with_nothing_linked_shows_an_error(self):
        orcid_count = Orcid.objects.count()

        response = self.client.post(reverse('edit_orcid'), {'remove_orcid': '1'})

        self.assertContains(response, 'No ORCID iD linked.')
        self.assertContains(response, 'Object Does Not Exist Error: tried to unlink an object which does not exist.')
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ['Object Does Not Exist Error: tried to unlink an object which does not exist.'])
        self.assertEqual(Orcid.objects.count(), orcid_count)


@override_settings(
    ROOT_URLCONF=__name__,
    ORCID_LOGIN_ENABLED=True,
    AUTHENTICATION_BACKENDS=settings.AUTHENTICATION_BACKENDS + ['user.backends.OrcidAuthBackend'],
    **ORCID_SETTINGS,
)
class OrcidLoginTests(TestCase):
    """
    Logging in, signing up and activating with ORCID. The login routes and backend are only
    registered when ORCID_LOGIN_ENABLED is set at startup, so this class adds them.
    """

    def start_login(self):
        response = self.client.get(reverse('orcid_init_login'))
        self.assertEqual(response.status_code, 302)
        return parse_qs(urlparse(response.url).query)['state'][0]

    def login(self, token):
        """
        Run the login flow with ORCID's token endpoint mocked to return `token`. The
        id_token signature check is mocked too, as it fetches ORCID's public keys;
        the view's access token validation still runs.
        """
        state = self.start_login()
        with patch('user.views.OAuth2Session.fetch_token', return_value=dict(token)) as mock_fetch_token:
            with patch('user.validators.validate_orcid_id_token') as mock_validate_id_token:
                response = self.client.get(reverse('auth_orcid_login'), {'code': 'abc123', 'state': state})
        mock_fetch_token.assert_called_once()
        mock_validate_id_token.assert_called_once_with(token['id_token'])
        return response

    def create_linked_user(self, is_active):
        user = User.objects.create_user(
            username='orcidlogin', email='orcidlogin@example.com', password='testpass123', is_active=is_active,
        )
        Orcid.objects.create(user=user, orcid_id=ORCID_TOKEN['orcid'])
        return user

    def activation_url(self, user, token):
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        return reverse('orcid_activate_user', kwargs={'uidb64': uidb64, 'token': token})

    def test_init_login_redirects_to_orcid(self):
        response = self.client.get(reverse('orcid_init_login'))

        self.assertEqual(response.status_code, 302)
        url = urlparse(response.url)
        query = parse_qs(url.query)
        self.assertEqual(f'{url.scheme}://{url.netloc}{url.path}', ORCID_SETTINGS['ORCID_AUTH_URL'])
        self.assertEqual(query['response_type'], ['code'])
        self.assertEqual(query['client_id'], [ORCID_SETTINGS['ORCID_CLIENT_ID']])
        self.assertEqual(query['redirect_uri'], [ORCID_SETTINGS['ORCID_LOGIN_REDIRECT_URI']])
        self.assertEqual(query['scope'], [ORCID_SETTINGS['ORCID_SCOPE']])
        self.assertEqual(query['state'], [self.client.session[views.ORCID_LOGIN_STATE_KEY]])

    def test_known_id_logs_the_user_in(self):
        user = self.create_linked_user(is_active=True)

        response = self.login(LOGIN_TOKEN)

        self.assertRedirects(response, reverse('login'), fetch_redirect_response=False)
        # The user id is only stored if authenticate() returned this user; the backend
        # is the one auth_orcid_login passes to login().
        self.assertEqual(self.client.session[SESSION_KEY], str(user.pk))
        self.assertEqual(self.client.session[BACKEND_SESSION_KEY], 'user.backends.OrcidAuthBackend')
        # The login also holds on the next request, which needs that backend to be listed.
        response = self.client.get(reverse('edit_orcid'))
        self.assertEqual(response.status_code, 200)

    def test_inactive_user_is_not_logged_in(self):
        user = self.create_linked_user(is_active=False)

        response = self.login(LOGIN_TOKEN)

        # This page is also what any user gets if OrcidAuthBackend is not listed;
        # test_known_id_logs_the_user_in covers that.
        self.assertTemplateUsed(response, 'user/register_done.html')
        self.assertContains(response, user.email)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_unknown_id_goes_to_sign_up(self):
        user_count = User.objects.count()

        response = self.login(LOGIN_TOKEN)

        self.assertRedirects(response, reverse('orcid_register'), fetch_redirect_response=False)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertEqual(User.objects.count(), user_count)
        self.assertFalse(Orcid.objects.filter(orcid_id=LOGIN_TOKEN['orcid']).exists())
        # Records current behavior: the whole token response, including the access,
        # refresh and id tokens, is kept in the session for the sign-up form. A later
        # change that keeps less will change this; update the test then.
        self.assertEqual(self.client.session['orcid_token'], LOGIN_TOKEN)

    def test_register_page_shows_the_form(self):
        self.login(LOGIN_TOKEN)

        response = self.client.get(reverse('orcid_register'))

        self.assertTemplateUsed(response, 'user/orcid_register.html')
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="first_names"')

    def test_register_creates_user_and_link(self):
        self.login(LOGIN_TOKEN)

        response = self.client.post(reverse('orcid_register'), {
            'email': 'orcidnew@example.com', 'username': 'orcidnew', 'first_names': 'Orcid', 'last_name': 'New',
            'privacy_policy': 'on',
        })

        self.assertTemplateUsed(response, 'user/register_done.html')
        user = User.objects.get(email='orcidnew@example.com')
        self.assertEqual(user.username, 'orcidnew')
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.first_names, 'Orcid')
        self.assertEqual(user.profile.last_name, 'New')
        orcid = Orcid.objects.get(user=user)
        self.assertEqual(orcid.orcid_id, LOGIN_TOKEN['orcid'])
        self.assertEqual(orcid.access_token, LOGIN_TOKEN['access_token'])
        self.assertEqual(orcid.refresh_token, LOGIN_TOKEN['refresh_token'])
        self.assertEqual(orcid.token_type, LOGIN_TOKEN['token_type'])
        self.assertEqual(orcid.token_scope, LOGIN_TOKEN['scope'])
        self.assertAlmostEqual(float(orcid.token_expiration), LOGIN_TOKEN['expires_at'], places=3)

        # One activation email, whose link opens the ORCID activation page for this user.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        link_match = re.search(r'(/orcid_activate/\S+)', mail.outbox[0].body)
        self.assertIsNotNone(link_match)
        match = resolve(link_match.group(1))
        self.assertEqual(match.func, views.activate_orcid_user)
        self.assertEqual(force_str(urlsafe_base64_decode(match.kwargs['uidb64'])), str(user.pk))
        self.assertTrue(default_token_generator.check_token(user, match.kwargs['token']))

    def test_activation_with_valid_link(self):
        user = self.create_linked_user(is_active=False)
        self.assertFalse(user.associated_emails.get(is_primary_email=True).is_verified)
        token = default_token_generator.make_token(user)

        with self.assertLogs('user.views', 'INFO'):
            response = self.client.get(self.activation_url(user, token))

        self.assertRedirects(response, reverse('orcid_init_login'), fetch_redirect_response=False)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ['The account has been activated.'])
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        email = user.associated_emails.get(is_primary_email=True)
        self.assertTrue(email.is_verified)
        self.assertIsNotNone(email.verification_date)

    def test_activation_with_invalid_link(self):
        user = self.create_linked_user(is_active=False)

        # The token has the shape the URL pattern accepts, so the view's own check rejects it.
        response = self.client.get(self.activation_url(user, 'abc-0123456789abcdef0123'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'user/activate_user_complete.html')
        self.assertEqual(response.context['title'], 'Invalid Activation Link')
        self.assertFalse(response.context['isvalid'])
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.associated_emails.get(is_primary_email=True).is_verified)

    def test_activation_of_active_user(self):
        user = self.create_linked_user(is_active=True)
        # The view returns before checking the token, so the token's validity doesn't matter.
        token = default_token_generator.make_token(user)

        response = self.client.get(self.activation_url(user, token))

        self.assertRedirects(response, reverse('login'), fetch_redirect_response=False)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertEqual(messages, ['The account is active.'])

    @override_settings(ORCID_LOGIN_ENABLED=False)
    @patch('user.views.OAuth2Session.fetch_token')
    def test_login_views_redirect_home_when_disabled(self, mock_fetch_token):
        # The routes are still in this class's URL configuration, so each view's own
        # check of ORCID_LOGIN_ENABLED is what refuses the request.
        user = self.create_linked_user(is_active=False)
        urls = [
            reverse('orcid_init_login'),
            reverse('auth_orcid_login') + '?code=abc123&state=anything',
            reverse('orcid_register'),
            self.activation_url(user, default_token_generator.make_token(user)),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)

        self.assertNotIn(views.ORCID_LOGIN_STATE_KEY, self.client.session)
        mock_fetch_token.assert_not_called()
        user.refresh_from_db()
        self.assertFalse(user.is_active)


@skipIf(settings.ORCID_LOGIN_ENABLED, 'ORCID login is enabled at startup in this environment')
class OrcidLoginDisabledTests(TestCase):
    """With ORCID_LOGIN_ENABLED off at startup, the ORCID login pages don't exist."""

    ACTIVATE_KWARGS = {'uidb64': 'MQ', 'token': 'abc-0123456789abcdef0123'}

    def test_login_urls_not_registered(self):
        for name in sorted(ORCID_LOGIN_URL_NAMES):
            # The activation route needs its arguments, or reverse() fails even when it exists.
            kwargs = self.ACTIVATE_KWARGS if name == 'orcid_activate_user' else None
            with self.subTest(name=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(name, kwargs=kwargs)

    def test_login_paths_not_found(self):
        paths = [
            '/orcid_init_login',
            '/authorcid_login/',
            '/orcid_register/',
            f"/orcid_activate/{self.ACTIVATE_KWARGS['uidb64']}/{self.ACTIVATE_KWARGS['token']}/",
        ]

        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


class OrcidUserHelperTests(TestCase):
    """User.has_orcid() and User.get_orcid_id()."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='orcidhelper', email='orcidhelper@example.com', password='testpass123',
        )

    def fresh_user(self):
        # Read the user again so the answers come from the database, not the
        # Orcid row (or its absence) cached on an earlier instance.
        return User.objects.get(pk=self.user.pk)

    def test_helpers_without_link(self):
        user = self.fresh_user()

        self.assertFalse(user.has_orcid())
        self.assertIsNone(user.get_orcid_id())

    def test_helpers_with_link(self):
        Orcid.objects.create(user=self.user, orcid_id=ORCID_TOKEN['orcid'])
        user = self.fresh_user()

        self.assertTrue(user.has_orcid())
        self.assertEqual(user.get_orcid_id(), ORCID_TOKEN['orcid'])

    def test_helpers_with_empty_id(self):
        # Records current behavior: has_orcid() only checks that a row exists, so a
        # row with an empty iD (as test_link_malformed_id_leaves_an_empty_row shows
        # auth_orcid can leave) counts as linked. A later change may treat it as not
        # linked; update the test then.
        Orcid.objects.create(user=self.user, orcid_id='')
        user = self.fresh_user()

        self.assertTrue(user.has_orcid())
        self.assertEqual(user.get_orcid_id(), '')
