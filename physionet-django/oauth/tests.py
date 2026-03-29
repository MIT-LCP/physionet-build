import base64
import random
import hashlib
from datetime import timedelta
import re
from django.test import TestCase
from django.utils import timezone
from user.models import User
from oauth2_provider.models import get_access_token_model, get_application_model
from django.urls import reverse
from urllib.parse import parse_qs, urlparse
from oauth2_provider.settings import oauth2_settings
from django.utils.crypto import get_random_string
from oauth.views import SCOPES_MAPPING


Application = get_application_model()
AccessToken = get_access_token_model()

CLEARTEXT_SECRET = "1234567890abcdefghijklmnopqrstuvwxyz"


class BaseTest(TestCase):
    def setUp(self, oauth2_settings=oauth2_settings):
        """
        Create a demo user, an OAuth Application and an access token for use in testing.
        """
        self.test_user = User.objects.create_user(
            username="oauth_test_user",
            email="oauth_test@example.com",
            password="123456",
        )

        self.dev_user = User.objects.create_user(
            username="oauth_dev_user", email="oauth_dev@example.com", password="123456"
        )

        self.test_user.profile.first_names = "OAuth"
        self.test_user.profile.last_name = "User"
        self.test_user.profile.affiliation = "MIT"
        self.test_user.profile.save()

        self.oauth2_settings = oauth2_settings

        self.application = Application.objects.create(
            name="Test Application",
            redirect_uris="http://localhost http://example.com http://example.org",
            user=self.dev_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret=CLEARTEXT_SECRET,
        )

        self.access_token = AccessToken.objects.create(
            user=self.test_user,
            scope="profile:read email:read public_id:read",
            expires=timezone.now() + timedelta(seconds=300),
            token="secret-access-token-key",
            application=self.application,
        )

    def _create_authorization_header(self, token):
        return "Bearer {0}".format(token)

    def get_basic_auth_header(self, user, password):
        """
        Return a dict containing the correct headers to set to make HTTP Basic
        Auth request
        """
        user_pass = "{0}:{1}".format(user, password)
        auth_string = base64.b64encode(user_pass.encode("utf-8"))
        auth_headers = {
            "HTTP_AUTHORIZATION": "Basic " + auth_string.decode("utf-8"),
        }

        return auth_headers


class TestOAuth2Authentication(BaseTest):
    def test_unauthenticated(self):
        """
        Hello is a demo resource endpoint that requires authentication. This test verifies that
        """
        response = self.client.get("/oauth/hello")
        self.assertEqual(response.status_code, 403)

    def test_authentication_allow(self):
        """
        This test verifies that a request with a valid access token is allowed.
        """
        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get("/oauth/hello", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)


class BaseAuthorizationCodeTokenView(BaseTest):
    def generate_pkce_codes(self, algorithm, length=43):
        """
        Generate a code verifier and a code challenge according to the PKCE
        """
        verifier = get_random_string(length=length)
        if algorithm == "S256":
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
        elif algorithm == "plain":
            challenge = verifier
        else:
            raise ValueError("Unsupported code challenge method.")

        return verifier, challenge

    def get_auth(self):
        """
        Helper method to retrieve a valid authorization code
        """

        authcode_data = {
            "client_id": self.application.client_id,
            "state": "random_state_string",
            "scope": "profile:read email:read public_id:read",
            "redirect_uri": "http://example.org",
            "response_type": "code",
            "allow": True,
        }

        response = self.client.post(
            reverse("oauth2_provider:authorize"), data=authcode_data
        )
        query_dict = parse_qs(urlparse(response["Location"]).query)
        return query_dict["code"].pop()

    def get_auth_pkce(self, code_challenge, code_challenge_method):
        """
        Helper method to retrieve a valid authorization code using pkce
        """
        authcode_data = {
            "client_id": self.application.client_id,
            "state": "random_state_string",
            "scope": "profile:read email:read public_id:read",
            "redirect_uri": "http://example.org",
            "response_type": "code",
            "allow": True,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }

        response = self.client.post(
            reverse("oauth2_provider:authorize"), data=authcode_data
        )
        query_dict = parse_qs(urlparse(response["Location"]).query)
        return query_dict["code"].pop()


class TestAuthorizationCodeTokenView(BaseAuthorizationCodeTokenView):
    def test_basic_auth(self):
        """
        Request an access token using basic authentication for client authentication
        """
        self.client.login(username="oauth_test_user", password="123456")

        # Disabled PKCE removes the need for a code_verifier
        # Checkout details on PKCE : https://oauth.net/2/pkce/
        self.oauth2_settings.PKCE_REQUIRED = False

        authorization_code = self.get_auth()

        token_request_data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": "http://example.org",
        }
        auth_headers = self.get_basic_auth_header(
            self.application.client_id, CLEARTEXT_SECRET
        )

        response = self.client.post(
            reverse("oauth2_provider:token"), data=token_request_data, **auth_headers
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]

        # Testing the Token Acquired through the above request
        self.client.logout()

        auth = self._create_authorization_header(token)
        response = self.client.get("/oauth/hello", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)

    def test_secure_auth_pkce(self):
        """
        Request an access token using client_type: public
        and PKCE enabled with the S256 algorithm
        """
        self.client.login(username="oauth_test_user", password="123456")

        self.application.client_type = Application.CLIENT_PUBLIC
        self.application.save()

        code_verifier, code_challenge = self.generate_pkce_codes("S256")
        authorization_code = self.get_auth_pkce(code_challenge, "S256")

        token_request_data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": "http://example.org",
            "code_verifier": code_verifier,
        }
        auth_headers = self.get_basic_auth_header(
            self.application.client_id, CLEARTEXT_SECRET
        )

        response = self.client.post(
            reverse("oauth2_provider:token"), data=token_request_data, **auth_headers
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]

        # Testing the Token Acquired through the above request
        self.client.logout()

        auth = self._create_authorization_header(token)
        response = self.client.get("/oauth/hello", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)


class TestOAuth2Scopes(BaseTest):
    def test_userinfo_scopes(self):
        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get("/oauth/userinfo", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["username"], self.test_user.username)
        self.assertEqual(data["full_name"], self.test_user.profile.get_full_name())
        self.assertEqual(data["email"], self.test_user.email)
        self.assertEqual(str(data["public_user_uuid"]), str(self.test_user.public_user_uuid))

    def test_userinfo_missing_scope(self):
        # Set only profile:read
        self.access_token.scope = "profile:read"
        self.access_token.save()

        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get("/oauth/userinfo", HTTP_AUTHORIZATION=auth)
        data = response.json()

        self.assertIn("username", data)
        self.assertNotIn("email", data)
        self.assertNotIn("public_user_uuid", data)


class TestUserInfoScopeValidation(BaseTest):
    def test_scope_fields_are_accessible(self):
        """
        Check that each field defined in SCOPES_MAPPING is present in the
        returned dictionary and corresponds to a valid attribute/method
        on the User or related objects.
        """
        for scope, builder in SCOPES_MAPPING.items():
            self.assertTrue(callable(builder), f"Scope '{scope}' does not map to a callable")

            try:
                result = builder(self.test_user)
            except Exception as e:
                self.fail(f"Callable for scope '{scope}' raised an exception: {e}")

            self.assertIsInstance(result, dict, f"Scope '{scope}' did not return a dictionary")
            for field, value in result.items():
                self.assertIsNotNone(field, f"Field name in scope '{scope}' is None")


class OIDCBaseTest(BaseTest):
    """Base test class that configures OIDC settings."""

    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        super().setUpClass()
        cls._test_rsa_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048,
        )
        cls.test_rsa_key_pem = cls._test_rsa_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode()
        cls.test_rsa_public_key = cls._test_rsa_key.public_key()

    def setUp(self):
        super().setUp()
        self.oauth2_settings.OIDC_ENABLED = True
        self.oauth2_settings.OIDC_RSA_PRIVATE_KEY = self.test_rsa_key_pem
        self.oauth2_settings.OIDC_ISS_ENDPOINT = "http://testserver"

    def tearDown(self):
        self.oauth2_settings.OIDC_ENABLED = False
        self.oauth2_settings.OIDC_RSA_PRIVATE_KEY = ""
        self.oauth2_settings.OIDC_ISS_ENDPOINT = None
        super().tearDown()


class TestOIDCDiscovery(OIDCBaseTest):
    def test_root_discovery_endpoint(self):
        response = self.client.get("/.well-known/openid-configuration")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["issuer"], "http://testserver")
        self.assertIn("authorization_endpoint", data)
        self.assertIn("token_endpoint", data)
        self.assertIn("userinfo_endpoint", data)
        self.assertIn("jwks_uri", data)
        self.assertIn("response_types_supported", data)
        self.assertIn("id_token_signing_alg_values_supported", data)

    def test_oauth_discovery_endpoint(self):
        response = self.client.get("/oauth/.well-known/openid-configuration")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["issuer"], "http://testserver")


class TestJWKSEndpoint(OIDCBaseTest):
    def test_jwks_returns_valid_keyset(self):
        response = self.client.get("/oauth/jwks/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("keys", data)
        self.assertGreater(len(data["keys"]), 0)

        key = data["keys"][0]
        self.assertEqual(key["kty"], "RSA")
        self.assertIn("n", key)
        self.assertIn("e", key)
        self.assertIn("kid", key)


class TestOIDCTokenFlow(OIDCBaseTest):
    def test_openid_scope_returns_id_token(self):
        """Authorization code flow with openid scope should return an id_token."""
        self.client.login(username="oauth_test_user", password="123456")

        authcode_data = {
            "client_id": self.application.client_id,
            "state": "random_state_string",
            "scope": "openid profile email",
            "redirect_uri": "http://example.org",
            "response_type": "code",
            "allow": True,
        }

        response = self.client.post(
            reverse("oauth2_provider:authorize"), data=authcode_data
        )
        query_dict = parse_qs(urlparse(response["Location"]).query)
        authorization_code = query_dict["code"].pop()

        token_request_data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": "http://example.org",
        }
        auth_headers = self.get_basic_auth_header(
            self.application.client_id, CLEARTEXT_SECRET
        )

        response = self.client.post(
            reverse("oauth2_provider:token"), data=token_request_data, **auth_headers
        )
        self.assertEqual(response.status_code, 200)
        token_data = response.json()
        self.assertIn("id_token", token_data)
        self.assertIn("access_token", token_data)

        # Decode and verify the ID token
        import jwt

        id_token = jwt.decode(
            token_data["id_token"],
            self.test_rsa_public_key,
            algorithms=["RS256"],
            audience=self.application.client_id,
        )
        self.assertEqual(id_token["iss"], "http://testserver")
        self.assertEqual(id_token["sub"], str(self.test_user.public_user_uuid))
        self.assertEqual(id_token["aud"], self.application.client_id)
        self.assertIn("exp", id_token)
        self.assertIn("iat", id_token)


class TestOIDCUserInfo(OIDCBaseTest):
    def test_oidc_userinfo_endpoint(self):
        """OIDC UserInfo endpoint (with trailing slash) returns standard claims."""
        self.access_token.scope = "openid profile email"
        self.access_token.save()

        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get("/oauth/userinfo/", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["sub"], str(self.test_user.public_user_uuid))
        self.assertIn("name", data)
        self.assertIn("email", data)

    def test_oidc_userinfo_without_token(self):
        response = self.client.get("/oauth/userinfo/")
        self.assertIn(response.status_code, [401, 403])


class TestLegacyUserInfoUnchanged(OIDCBaseTest):
    def test_legacy_userinfo_still_works(self):
        """Legacy /oauth/userinfo (no trailing slash) still returns the old format."""
        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get("/oauth/userinfo", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Legacy format uses "username" and "full_name", not OIDC claim names
        self.assertIn("username", data)
        self.assertIn("full_name", data)
        # Should NOT contain OIDC-specific claim names
        self.assertNotIn("sub", data)
        self.assertNotIn("preferred_username", data)
