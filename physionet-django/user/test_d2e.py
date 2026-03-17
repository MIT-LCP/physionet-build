from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from user.models import D2eAccount

User = get_user_model()


class D2eEditViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )
        self.user.is_active = True
        self.user.save()

    def test_edit_d2e_requires_login(self):
        response = self.client.get(reverse('edit_d2e'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    @override_settings(
        D2E_CLIENT_ID='test-client-id',
        D2E_AUTH_URL='https://logto.example.com/oidc/auth',
        D2E_SCOPE='openid profile email',
    )
    def test_edit_d2e_initiates_oidc_flow(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('edit_d2e'), {'request_d2e': '1'})

        self.assertEqual(response.status_code, 302)
        self.assertIn('logto.example.com/oidc/auth', response.url)
        self.assertIn('client_id=test-client-id', response.url)
        self.assertIn('response_type=code', response.url)
        self.assertIn('state=', response.url)
        self.assertIn('nonce=', response.url)

        # Both state and nonce stored in session
        self.assertIn('d2e_state', self.client.session)
        self.assertIn('d2e_nonce', self.client.session)
        self.assertEqual(len(self.client.session['d2e_state']), 32)
        self.assertEqual(len(self.client.session['d2e_nonce']), 32)

    def test_edit_d2e_missing_config(self):
        self.client.force_login(self.user)

        with override_settings(D2E_CLIENT_ID=None):
            response = self.client.post(reverse('edit_d2e'), {'request_d2e': '1'})

        msgs = list(get_messages(response.wsgi_request))
        self.assertEqual(len(msgs), 1)
        self.assertIn('configuration is incomplete', str(msgs[0]))

    def test_remove_d2e_account(self):
        self.client.force_login(self.user)
        D2eAccount.objects.create(
            user=self.user,
            sub='logto-sub-123',
            name='Test User',
            email='test@d2e.com',
        )

        response = self.client.post(reverse('edit_d2e'), {'remove_d2e': '1'})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(D2eAccount.objects.filter(user=self.user).exists())
        msgs = list(get_messages(response.wsgi_request))
        self.assertIn('unlinked', str(msgs[0]).lower())

    def test_remove_d2e_no_account(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('edit_d2e'), {'remove_d2e': '1'})

        msgs = list(get_messages(response.wsgi_request))
        self.assertIn('No D2E account', str(msgs[0]))


@override_settings(
    D2E_CLIENT_ID='test-client-id',
    D2E_CLIENT_SECRET='test-secret',
    D2E_TOKEN_URL='https://logto.example.com/oidc/token',
    D2E_USERINFO_URL='https://logto.example.com/oidc/me',
    D2E_JWKS_URL='https://logto.example.com/oidc/jwks',
    D2E_LINK_REDIRECT_URI='http://testserver/d2e/callback/',
    D2E_OIDC_ISSUER='https://logto.example.com/oidc',
)
class D2eAuthCallbackTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )
        self.user.is_active = True
        self.user.save()

        self.mock_token_response = {
            'access_token': 'mock-access-token',
            'refresh_token': 'mock-refresh-token',
            'token_type': 'Bearer',
            'expires_in': 3600,
            'id_token': 'mock-id-token',
        }

        self.mock_userinfo_response = {
            'sub': 'logto-sub-123',
            'name': 'Test User',
            'email': 'testuser@d2e.example.com',
        }

    def _set_session_state(self, state='test-state-12345678901234567890', nonce='test-nonce-12345678901234567890'):
        session = self.client.session
        session['d2e_state'] = state
        session['d2e_nonce'] = nonce
        session.save()
        return state

    def test_auth_d2e_requires_login(self):
        response = self.client.get(reverse('auth_d2e'), {'code': 'test-code', 'state': 'x'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_auth_d2e_state_mismatch(self):
        self.client.force_login(self.user)
        self._set_session_state(state='expected-state')

        response = self.client.get(reverse('auth_d2e'), {'code': 'test-code', 'state': 'wrong-state'})

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Invalid linking session' in str(m) for m in msgs))

    def test_auth_d2e_no_session_state(self):
        self.client.force_login(self.user)
        # No state in session

        response = self.client.get(reverse('auth_d2e'), {'code': 'test-code', 'state': 'any-state'})

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Invalid linking session' in str(m) for m in msgs))

    def test_auth_d2e_error_callback(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('auth_d2e'), {
            'error': 'access_denied',
            'error_description': 'User denied access',
        })

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('User denied access' in str(m) for m in msgs))

    def test_auth_d2e_missing_code(self):
        self.client.force_login(self.user)
        state = self._set_session_state()

        response = self.client.get(reverse('auth_d2e'), {'state': state})

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Missing authorization code' in str(m) for m in msgs))

    @patch('user.views.requests.post')
    def test_token_exchange_failure(self, mock_post):
        self.client.force_login(self.user)
        state = self._set_session_state()

        mock_post_response = Mock()
        mock_post_response.status_code = 400
        mock_post_response.text = 'Bad request'
        mock_post.return_value = mock_post_response

        response = self.client.get(reverse('auth_d2e'), {'code': 'bad-code', 'state': state})

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Failed to exchange' in str(m) for m in msgs))
        self.assertFalse(D2eAccount.objects.filter(user=self.user).exists())

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_successful_d2e_linking_via_userinfo(self, mock_get, mock_post):
        """Test linking when ID token verification falls back to userinfo."""
        self.client.force_login(self.user)
        state = self._set_session_state()

        # Token exchange succeeds but without id_token
        token_without_id = dict(self.mock_token_response)
        del token_without_id['id_token']
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = token_without_id
        mock_post.return_value = mock_post_response

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = self.mock_userinfo_response
        mock_get.return_value = mock_get_response

        response = self.client.get(reverse('auth_d2e'), {'code': 'test-code', 'state': state})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('edit_d2e'))
        self.assertTrue(D2eAccount.objects.filter(user=self.user).exists())

        account = D2eAccount.objects.get(user=self.user)
        self.assertEqual(account.sub, 'logto-sub-123')
        self.assertEqual(account.name, 'Test User')
        self.assertEqual(account.email, 'testuser@d2e.example.com')
        self.assertEqual(account.access_token, 'mock-access-token')
        self.assertEqual(account.refresh_token, 'mock-refresh-token')

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('linked' in str(m).lower() for m in msgs))

        # Session state should be consumed
        self.assertNotIn('d2e_state', self.client.session)
        self.assertNotIn('d2e_nonce', self.client.session)

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_d2e_account_already_linked_to_another_user(self, mock_get, mock_post):
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123',
        )
        other_user.is_active = True
        other_user.save()

        D2eAccount.objects.create(
            user=other_user,
            sub='logto-sub-123',
            name='Other User',
            email='other@d2e.com',
        )

        self.client.force_login(self.user)
        state = self._set_session_state()

        token_without_id = dict(self.mock_token_response)
        del token_without_id['id_token']
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = token_without_id
        mock_post.return_value = mock_post_response

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = self.mock_userinfo_response
        mock_get.return_value = mock_get_response

        response = self.client.get(reverse('auth_d2e'), {'code': 'test-code', 'state': state})

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('already linked to another user' in str(m).lower() for m in msgs))
        self.assertFalse(D2eAccount.objects.filter(user=self.user).exists())

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_update_existing_d2e_account(self, mock_get, mock_post):
        self.client.force_login(self.user)

        D2eAccount.objects.create(
            user=self.user,
            sub='logto-sub-123',
            name='Old Name',
            email='old@d2e.com',
        )

        state = self._set_session_state()

        token_without_id = dict(self.mock_token_response)
        del token_without_id['id_token']
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = token_without_id
        mock_post.return_value = mock_post_response

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = self.mock_userinfo_response
        mock_get.return_value = mock_get_response

        self.client.get(reverse('auth_d2e'), {'code': 'test-code', 'state': state})

        self.assertEqual(D2eAccount.objects.filter(user=self.user).count(), 1)
        account = D2eAccount.objects.get(user=self.user)
        self.assertEqual(account.name, 'Test User')
        self.assertEqual(account.email, 'testuser@d2e.example.com')

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_userinfo_failure(self, mock_get, mock_post):
        self.client.force_login(self.user)
        state = self._set_session_state()

        token_without_id = dict(self.mock_token_response)
        del token_without_id['id_token']
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = token_without_id
        mock_post.return_value = mock_post_response

        mock_get_response = Mock()
        mock_get_response.status_code = 500
        mock_get_response.text = 'Internal server error'
        mock_get.return_value = mock_get_response

        response = self.client.get(reverse('auth_d2e'), {'code': 'test-code', 'state': state})

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Failed to retrieve D2E user information' in str(m) for m in msgs))

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_missing_sub_in_response(self, mock_get, mock_post):
        self.client.force_login(self.user)
        state = self._set_session_state()

        token_without_id = dict(self.mock_token_response)
        del token_without_id['id_token']
        mock_post_response = Mock()
        mock_post_response.status_code = 200
        mock_post_response.json.return_value = token_without_id
        mock_post.return_value = mock_post_response

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {'name': 'No Sub', 'email': 'nosub@d2e.com'}
        mock_get.return_value = mock_get_response

        response = self.client.get(reverse('auth_d2e'), {'code': 'test-code', 'state': state})

        msgs = list(get_messages(response.wsgi_request))
        self.assertTrue(any('subject identifier not found' in str(m).lower() for m in msgs))


class D2eModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )

    def test_create_d2e_account(self):
        account = D2eAccount.objects.create(
            user=self.user,
            sub='logto-sub-123',
            name='Test User',
            email='test@d2e.com',
            access_token='token',
            refresh_token='refresh',
            token_type='Bearer',
        )

        self.assertEqual(account.user, self.user)
        self.assertEqual(account.sub, 'logto-sub-123')

    def test_d2e_account_str(self):
        account = D2eAccount.objects.create(
            user=self.user,
            sub='logto-sub-789',
            name='John Doe',
            email='john@d2e.com',
        )

        self.assertIn('John Doe', str(account))
        self.assertIn('logto-sub-789', str(account))

    def test_one_d2e_account_per_user(self):
        D2eAccount.objects.create(
            user=self.user,
            sub='logto-sub-first',
            name='Test User',
            email='test@d2e.com',
        )

        with self.assertRaises(Exception):
            D2eAccount.objects.create(
                user=self.user,
                sub='logto-sub-second',
                name='Test User',
                email='test2@d2e.com',
            )

    def test_unique_sub(self):
        D2eAccount.objects.create(
            user=self.user,
            sub='logto-sub-unique',
            name='User 1',
            email='u1@d2e.com',
        )

        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123',
        )

        with self.assertRaises(Exception):
            D2eAccount.objects.create(
                user=other_user,
                sub='logto-sub-unique',
                name='User 2',
                email='u2@d2e.com',
            )
