"""
Tests for KHDP OAuth account linking functionality.

Tests cover:
- Successful account linking with all fields
- Successful account linking without optional fields (orcid, physionet_id)
- CSRF protection (nonce validation)
- Account already linked to another user
- Unauthenticated access
- Error scenarios (token exchange, userinfo, validation, database)
"""
from unittest.mock import Mock, patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse

from user.models import KhdpAccount

User = get_user_model()


class KhdpEditViewTests(TestCase):
    """Tests for the edit_khdp view (KHDP settings page)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )
        self.user.is_active = True
        self.user.save()

    def test_edit_khdp_requires_login(self):
        """Test that edit_khdp requires authentication."""
        response = self.client.get(reverse('edit_khdp'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    @override_settings(
        KHDP_CLIENT_ID='test-client-id',
        KHDP_AUTH_URL='https://khdp.example.com/oauth/authorize',
    )
    def test_edit_khdp_initiates_oauth_flow(self):
        """Test that POST request initiates OAuth flow with correct parameters."""
        self.client.force_login(self.user)

        response = self.client.post(reverse('edit_khdp'), {'request_khdp': '1'})

        # Should redirect to KHDP authorization URL
        self.assertEqual(response.status_code, 302)
        self.assertIn('khdp.example.com/oauth/authorize', response.url)
        self.assertIn('appId=test-client-id', response.url)
        self.assertIn('redirectUrl=', response.url)
        self.assertIn('nonce=', response.url)

        # Should store nonce in session
        self.assertIn('khdp_nonce', self.client.session)
        self.assertEqual(len(self.client.session['khdp_nonce']), 32)

    def test_edit_khdp_missing_config(self):
        """Test that missing KHDP config shows error message."""
        self.client.force_login(self.user)

        with override_settings(KHDP_CLIENT_ID=None):
            response = self.client.post(reverse('edit_khdp'), {'request_khdp': '1'})

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('configuration is incomplete', str(messages[0]))


@override_settings(
    KHDP_CLIENT_ID='test-client-id',
    KHDP_CLIENT_SECRET='test-secret',
    KHDP_TOKEN_URL='https://khdp.example.com/oauth/token',
    KHDP_USERINFO_URL='https://khdp.example.com/oauth/userinfo',
    KHDP_LINK_REDIRECT_URI='http://testserver/khdp/',
)
class KhdpAuthCallbackTests(TestCase):
    """Tests for the auth_khdp view (OAuth callback handler)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )
        self.user.is_active = True
        self.user.save()

        # Mock KHDP responses
        self.mock_token_response = {
            'accessToken': 'mock-access-token',
            'tokenType': 'Bearer',
            'expires_in': 3600,
            'idToken': 'mock-id-token',
        }

        self.mock_userinfo_response = {
            'publicUuid': 'khdp-public-uuid-123',
            'userId': 'khdp-user-123',
            'userName': 'Test User',
            'affiliation': 'Test University',
            'mail': 'testuser@khdp.example.com',
            'orcid': '0000-0001-2345-6789',
            'physionetId': 'pn-uuid-123',
        }

    def test_auth_khdp_requires_login(self):
        """Test that auth_khdp requires authentication."""
        response = self.client.get(reverse('auth_khdp'), {'code': 'test-code'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_auth_khdp_requires_code_parameter(self):
        """Test that missing authorization code shows error."""
        self.client.force_login(self.user)
        session = self.client.session
        session['khdp_nonce'] = 'test-nonce-12345678901234567890'
        session.save()

        response = self.client.get(reverse('auth_khdp'))

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Missing authorization code', str(messages[0]))

    def test_auth_khdp_requires_nonce_in_session(self):
        """Test CSRF protection - rejects callback without nonce in session."""
        self.client.force_login(self.user)

        # No nonce in session
        response = self.client.get(reverse('auth_khdp'), {'code': 'test-code'})

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Invalid linking session', str(messages[0]))
        self.assertEqual(response.status_code, 302)

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_successful_khdp_linking_with_all_fields(self, mock_get, mock_post):
        """Test successful KHDP account linking with all fields present."""
        self.client.force_login(self.user)

        # Set up session with nonce
        session = self.client.session
        session['khdp_nonce'] = 'test-nonce-12345678901234567890'
        session.save()

        # Mock token exchange response
        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = self.mock_token_response
        mock_post.return_value = mock_post_response

        # Mock userinfo response
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = self.mock_userinfo_response
        mock_get.return_value = mock_get_response

        # Make callback request
        response = self.client.get(reverse('auth_khdp'), {'code': 'test-auth-code'})

        # Verify redirect to edit_khdp
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('edit_khdp'))

        # Verify KhdpAccount was created
        self.assertTrue(KhdpAccount.objects.filter(user=self.user).exists())

        khdp_account = KhdpAccount.objects.get(user=self.user)
        self.assertEqual(khdp_account.khdp_user_id, 'khdp-user-123')
        self.assertEqual(khdp_account.name, 'Test User')
        self.assertEqual(khdp_account.affiliation, 'Test University')
        self.assertEqual(khdp_account.email, 'testuser@khdp.example.com')
        self.assertEqual(khdp_account.orcid, '0000-0001-2345-6789')
        self.assertEqual(khdp_account.physionet_id, 'pn-uuid-123')
        self.assertEqual(khdp_account.access_token, 'mock-access-token')
        self.assertEqual(khdp_account.token_type, 'Bearer')

        # Verify success message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('linked', str(messages[0]).lower())

        # Verify nonce was removed from session
        self.assertNotIn('khdp_nonce', self.client.session)

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_successful_khdp_linking_without_optional_fields(self, mock_get, mock_post):
        """Test successful KHDP account linking when orcid and physionet_id are missing."""
        self.client.force_login(self.user)

        # Set up session with nonce
        session = self.client.session
        session['khdp_nonce'] = 'test-nonce-12345678901234567890'
        session.save()

        # Mock token exchange
        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = self.mock_token_response
        mock_post.return_value = mock_post_response

        # Mock userinfo WITHOUT orcid and physionetId
        mock_userinfo = {
            'publicUuid': 'khdp-public-uuid-456',
            'userId': 'khdp-user-456',
            'userName': 'User Without ORCID',
            'affiliation': 'Another University',
            'mail': 'noorcid@khdp.example.com',
            'orcid': None,
            'physionetId': None,
        }
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = mock_userinfo
        mock_get.return_value = mock_get_response

        # Make callback request
        response = self.client.get(reverse('auth_khdp'), {'code': 'test-auth-code'})

        # Verify account was created successfully
        self.assertEqual(response.status_code, 302)
        self.assertTrue(KhdpAccount.objects.filter(user=self.user).exists())

        khdp_account = KhdpAccount.objects.get(user=self.user)
        self.assertEqual(khdp_account.khdp_user_id, 'khdp-user-456')
        self.assertEqual(khdp_account.orcid, '')  # Should be empty string, not None
        self.assertEqual(khdp_account.physionet_id, '')  # Should be empty string, not None

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_khdp_account_already_linked_to_another_user(self, mock_get, mock_post):
        """Test that KHDP account already linked to another user is rejected."""
        # Create another user with existing KHDP account
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123',
        )
        other_user.is_active = True
        other_user.save()

        KhdpAccount.objects.create(
            user=other_user,
            public_uuid='other-user-uuid-123',
            khdp_user_id='khdp-user-123',  # Same KHDP user ID
            name='Other User',
            affiliation='Other Org',
            email='other@khdp.com',
        )

        self.client.force_login(self.user)

        # Set up session
        session = self.client.session
        session['khdp_nonce'] = 'test-nonce-12345678901234567890'
        session.save()

        # Mock responses
        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = self.mock_token_response
        mock_post.return_value = mock_post_response

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = self.mock_userinfo_response
        mock_get.return_value = mock_get_response

        # Make callback request
        response = self.client.get(reverse('auth_khdp'), {'code': 'test-auth-code'})

        # Should show error message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('already linked to another user' in str(m).lower() for m in messages)
        )

        # Should NOT create a new KhdpAccount for this user
        self.assertFalse(KhdpAccount.objects.filter(user=self.user).exists())

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_update_existing_khdp_account(self, mock_get, mock_post):
        """Test updating an existing KHDP account for the same user."""
        self.client.force_login(self.user)

        # Create existing KhdpAccount
        existing_account = KhdpAccount.objects.create(
            user=self.user,
            public_uuid='existing-uuid-123',
            khdp_user_id='khdp-user-123',
            name='Old Name',
            affiliation='Old Affiliation',
            email='old@khdp.com',
            orcid='old-orcid',
        )

        # Set up session
        session = self.client.session
        session['khdp_nonce'] = 'test-nonce-12345678901234567890'
        session.save()

        # Mock responses with updated data
        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = self.mock_token_response
        mock_post.return_value = mock_post_response

        updated_userinfo = {
            'publicUuid': 'khdp-public-uuid-updated',
            'userId': 'khdp-user-123',  # Same user ID
            'userName': 'Updated Name',
            'affiliation': 'Updated University',
            'mail': 'updated@khdp.com',
            'orcid': '0000-0001-9999-8888',
        }
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = updated_userinfo
        mock_get.return_value = mock_get_response

        # Make callback request
        self.client.get(reverse('auth_khdp'), {'code': 'test-auth-code'})

        # Should still have only one KhdpAccount
        self.assertEqual(KhdpAccount.objects.filter(user=self.user).count(), 1)

        # Account should be updated
        existing_account.refresh_from_db()
        self.assertEqual(existing_account.name, 'Updated Name')
        self.assertEqual(existing_account.affiliation, 'Updated University')
        self.assertEqual(existing_account.email, 'updated@khdp.com')
        self.assertEqual(existing_account.orcid, '0000-0001-9999-8888')

    @patch('user.views.requests.post')
    def test_token_exchange_failure(self, mock_post):
        """Test handling of token exchange failure."""
        self.client.force_login(self.user)

        session = self.client.session
        session['khdp_nonce'] = 'test-nonce-12345678901234567890'
        session.save()

        # Mock failed token exchange
        mock_post_response = Mock()
        mock_post_response.status_code = 400
        mock_post_response.text = 'Invalid authorization code'
        mock_post.return_value = mock_post_response

        response = self.client.get(reverse('auth_khdp'), {'code': 'invalid-code'})

        # Should show error message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('Failed to exchange authorization code' in str(m) for m in messages)
        )

        # Should not create KhdpAccount
        self.assertFalse(KhdpAccount.objects.filter(user=self.user).exists())

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_userinfo_endpoint_failure(self, mock_get, mock_post):
        """Test handling of userinfo endpoint failure."""
        self.client.force_login(self.user)

        session = self.client.session
        session['khdp_nonce'] = 'test-nonce-12345678901234567890'
        session.save()

        # Token exchange succeeds
        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = self.mock_token_response
        mock_post.return_value = mock_post_response

        # Userinfo fails
        mock_get_response = Mock()
        mock_get_response.status_code = 500
        mock_get_response.text = 'Internal server error'
        mock_get.return_value = mock_get_response

        response = self.client.get(reverse('auth_khdp'), {'code': 'test-code'})

        # Should show error message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('Failed to retrieve KHDP user information' in str(m) for m in messages)
        )

    @patch('user.views.requests.post')
    @patch('user.views.requests.get')
    def test_missing_userid_in_response(self, mock_get, mock_post):
        """Test handling when userId is missing from KHDP response."""
        self.client.force_login(self.user)

        session = self.client.session
        session['khdp_nonce'] = 'test-nonce-12345678901234567890'
        session.save()

        # Token exchange succeeds
        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = self.mock_token_response
        mock_post.return_value = mock_post_response

        # Mock userinfo response without userId
        incomplete_userinfo = {
            'publicUuid': 'khdp-public-uuid-incomplete',
            'userName': 'Test User',
            'mail': 'test@khdp.com',
            # Missing userId
        }
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = incomplete_userinfo
        mock_get.return_value = mock_get_response

        response = self.client.get(reverse('auth_khdp'), {'code': 'test-code'})

        # Should show error message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('user identifier not found' in str(m).lower() for m in messages)
        )


class KhdpModelTests(TestCase):
    """Tests for the KhdpAccount model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )

    def test_create_khdp_account_with_all_fields(self):
        """Test creating KhdpAccount with all fields."""
        account = KhdpAccount.objects.create(
            user=self.user,
            public_uuid='test-uuid-123',
            khdp_user_id='khdp-123',
            name='Test User',
            affiliation='Test Org',
            email='test@khdp.com',
            orcid='0000-0001-2345-6789',
            physionet_id='pn-uuid-123',
            access_token='token',
            token_type='Bearer',
        )

        self.assertEqual(account.user, self.user)
        self.assertEqual(account.khdp_user_id, 'khdp-123')
        self.assertEqual(account.orcid, '0000-0001-2345-6789')

    def test_create_khdp_account_without_optional_fields(self):
        """Test creating KhdpAccount without orcid and physionet_id."""
        account = KhdpAccount.objects.create(
            user=self.user,
            public_uuid='test-uuid-456',
            khdp_user_id='khdp-456',
            name='Test User',
            affiliation='Test Org',
            email='test@khdp.com',
            # orcid not provided - should default to ''
            # physionet_id not provided - should default to ''
        )

        self.assertEqual(account.orcid, '')
        self.assertEqual(account.physionet_id, '')

    def test_khdp_account_str_method(self):
        """Test string representation of KhdpAccount."""
        account = KhdpAccount.objects.create(
            user=self.user,
            public_uuid='test-uuid-789',
            khdp_user_id='khdp-789',
            name='John Doe',
            affiliation='Test Org',
            email='test@khdp.com',
        )

        self.assertIn('John Doe', str(account))
        self.assertIn('khdp-789', str(account))

    def test_one_khdp_account_per_user(self):
        """Test that each user can have only one KHDP account."""
        KhdpAccount.objects.create(
            user=self.user,
            public_uuid='test-uuid-first',
            khdp_user_id='khdp-first',
            name='Test User',
            affiliation='Test Org',
            email='test@khdp.com',
        )

        # Attempting to create another should fail (OneToOneField constraint)
        with self.assertRaises(Exception):
            KhdpAccount.objects.create(
                user=self.user,
                public_uuid='test-uuid-second',
                khdp_user_id='khdp-second',
                name='Test User',
                affiliation='Test Org',
                email='test2@khdp.com',
            )
