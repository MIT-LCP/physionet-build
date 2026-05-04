import base64
import hashlib
import os
import random
import re
import tempfile
from datetime import timedelta
from io import StringIO
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from oauth2_provider.models import get_access_token_model, get_application_model
from oauth2_provider.settings import oauth2_settings

from oauth.models import Partner
from oauth.views import SCOPES_MAPPING
from physionet.settings.base import load_oidc_provider_config
from user.models import User


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

        non_pkce_settings = {**settings.OAUTH2_PROVIDER, "PKCE_REQUIRED": False}
        with override_settings(OAUTH2_PROVIDER=non_pkce_settings):
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
    """
    Base test class that enables the OIDC provider with a freshly generated
    RSA signing key, scoped to the lifetime of the class.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Generate a temporary RSA key for signing test ID tokens
        cls._test_rsa_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048,
        )
        cls.test_rsa_key_pem = cls._test_rsa_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        cls.test_rsa_public_key = cls._test_rsa_key.public_key()

        # Enable OIDC via override_settings so the change is rolled back even
        # if a test fails mid-run, instead of leaking into sibling tests.
        oidc_overrides = {
            **settings.OAUTH2_PROVIDER,
            "OIDC_ENABLED": True,
            "OIDC_RSA_PRIVATE_KEY": cls.test_rsa_key_pem,
            "OIDC_ISS_ENDPOINT": "http://testserver",
        }
        cls._settings_override = override_settings(OAUTH2_PROVIDER=oidc_overrides)
        cls._settings_override.enable()
        cls.addClassCleanup(cls._settings_override.disable)

    def setUp(self):
        super().setUp()
        # OIDC ID-token signing requires the Application to opt in to RS256;
        # the BaseTest default leaves algorithm blank so the OAuth2-only flow works.
        self.application.algorithm = Application.RS256_ALGORITHM
        self.application.save()


class TestOIDCDiscovery(OIDCBaseTest):
    """
    Test the OIDC discovery document is served at the spec-mandated root
    location and from the oauth/ namespace.
    """

    def test_root_discovery_endpoint(self):
        """The discovery document is served at /.well-known/openid-configuration."""
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
        """The discovery document is also reachable under the oauth/ namespace."""
        response = self.client.get("/oauth/.well-known/openid-configuration")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["issuer"], "http://testserver")

    def test_advertises_introspection_endpoint(self):
        """The discovery document publishes the introspection_endpoint."""
        response = self.client.get("/.well-known/openid-configuration")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["introspection_endpoint"],
            "http://testserver/oauth/introspect/",
        )

    def test_advertises_end_session_endpoint(self):
        """The discovery document publishes the end_session_endpoint."""
        response = self.client.get("/.well-known/openid-configuration")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["end_session_endpoint"],
            "http://testserver/oauth/end-session/",
        )


class TestJWKSEndpoint(OIDCBaseTest):
    """
    Test the JWKS endpoint publishes the active signing key in the format
    relying parties need to verify ID token signatures.
    """

    def test_jwks_returns_valid_keyset(self):
        """JWKS publishes an RSA key with the required JWK fields."""
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
    """
    Test the OpenID Connect authorization code flow returns a signed ID
    token alongside the access token, with the expected standard claims.
    """

    def test_openid_scope_returns_id_token(self):
        """An auth code flow with the openid scope returns a verifiable id_token."""
        self.client.login(username="oauth_test_user", password="123456")

        # Use a fresh Application created with RS256 from the start. Mutating
        # self.application.algorithm post-creation is unreliable when an earlier
        # test class has touched DOT's internal application/grant-type state.
        oidc_secret = "1234567890abcdefghijklmnopqrstuvwxyz"
        oidc_app = Application.objects.create(
            name="OIDC Token Test App",
            redirect_uris="http://example.org",
            user=self.dev_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            algorithm=Application.RS256_ALGORITHM,
            client_secret=oidc_secret,
        )

        # PKCE_REQUIRED defaults True; disable it for this confidential-client flow.
        non_pkce = {**settings.OAUTH2_PROVIDER, "PKCE_REQUIRED": False}

        with override_settings(OAUTH2_PROVIDER=non_pkce):
            # Request authorization with the standard OIDC scopes
            authcode_data = {
                "client_id": oidc_app.client_id,
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

            # Exchange the code for tokens
            token_request_data = {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": "http://example.org",
            }
            auth_headers = self.get_basic_auth_header(
                oidc_app.client_id, oidc_secret,
            )

            response = self.client.post(
                reverse("oauth2_provider:token"), data=token_request_data, **auth_headers
            )
        self.assertEqual(response.status_code, 200)
        token_data = response.json()
        self.assertIn("id_token", token_data)
        self.assertIn("access_token", token_data)

        # Verify the ID token signature and standard claims
        id_token = jwt.decode(
            token_data["id_token"],
            self.test_rsa_public_key,
            algorithms=["RS256"],
            audience=oidc_app.client_id,
        )
        self.assertEqual(id_token["iss"], "http://testserver")
        self.assertEqual(id_token["sub"], str(self.test_user.public_user_uuid))
        self.assertEqual(id_token["aud"], oidc_app.client_id)
        self.assertIn("exp", id_token)
        self.assertIn("iat", id_token)


class TestOIDCUserInfo(OIDCBaseTest):
    """
    Test the OIDC UserInfo endpoint returns standard claims and is correctly
    advertised in the discovery document.
    """

    def test_oidc_userinfo_endpoint(self):
        """A token with openid scope returns standard OIDC claims from UserInfo."""
        self.access_token.scope = "openid profile email"
        self.access_token.save()

        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get("/oauth/oidc/userinfo", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["sub"], str(self.test_user.public_user_uuid))
        self.assertIn("name", data)
        self.assertIn("email", data)

    def test_oidc_userinfo_without_token(self):
        """The UserInfo endpoint rejects unauthenticated requests."""
        response = self.client.get("/oauth/oidc/userinfo")
        self.assertIn(response.status_code, [401, 403])

    def test_oidc_discovery_advertises_correct_userinfo(self):
        """The discovery document points clients at the OIDC userinfo path."""
        response = self.client.get("/.well-known/openid-configuration")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["userinfo_endpoint"],
            "http://testserver/oauth/oidc/userinfo",
        )


class TestLegacyUserInfoUnchanged(OIDCBaseTest):
    """
    Test that adding the OIDC provider has not broken the pre-existing
    /oauth/userinfo resource endpoint, which legacy clients continue to use.
    """

    def test_legacy_userinfo_still_works(self):
        """Legacy /oauth/userinfo still returns the original (non-OIDC) format."""
        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get("/oauth/userinfo", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Legacy format uses "username" and "full_name", not OIDC claim names
        self.assertIn("username", data)
        self.assertIn("full_name", data)
        self.assertNotIn("sub", data)
        self.assertNotIn("preferred_username", data)

    def test_legacy_userinfo_with_trailing_slash_works(self):
        """Both /oauth/userinfo and /oauth/userinfo/ resolve to the legacy view."""
        # Regression: /oauth/userinfo/ used to route to OIDCUserInfoView and
        # reject legacy tokens with 401.
        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get("/oauth/userinfo/", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("username", data)
        self.assertNotIn("sub", data)


class TestOIDCDiscoveryRestrictsResponseTypes(OIDCBaseTest):
    """
    Test that the discovery document advertises only the authorization-code
    flow, since implicit and hybrid flows are deprecated by OAuth 2.1.
    """

    def test_response_types_supported_is_code_only(self):
        """response_types_supported lists 'code' and nothing else."""
        response = self.client.get("/.well-known/openid-configuration")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["response_types_supported"], ["code"])


class TestOIDCKeyRotation(OIDCBaseTest):
    """
    Test that rotated-out signing keys configured via OIDC_RSA_PRIVATE_KEYS_INACTIVE
    are still published in JWKS so relying parties can verify tokens issued
    under the previous key during the rotation overlap window.
    """

    def test_inactive_keys_are_published_in_jwks(self):
        """JWKS publishes the active key plus every key listed in OIDC_RSA_PRIVATE_KEYS_INACTIVE."""
        # Generate an additional RSA key to act as a rotated-out signer
        old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        old_key_pem = old_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()

        rotation_settings = {
            **settings.OAUTH2_PROVIDER,
            "OIDC_ENABLED": True,
            "OIDC_RSA_PRIVATE_KEY": self.test_rsa_key_pem,
            "OIDC_RSA_PRIVATE_KEYS_INACTIVE": [old_key_pem],
            "OIDC_ISS_ENDPOINT": "http://testserver",
        }
        with override_settings(OAUTH2_PROVIDER=rotation_settings):
            response = self.client.get("/oauth/jwks/")

        self.assertEqual(response.status_code, 200)
        keys = response.json()["keys"]
        self.assertEqual(len(keys), 2)
        # Each published key carries a distinct kid
        self.assertEqual(len({k["kid"] for k in keys}), 2)


class TestOIDCClaimScopes(OIDCBaseTest):
    """
    Test that each OIDC scope contributes its expected claims to the UserInfo
    response, covering the per-scope branches in CustomOAuth2Validator._build_claims.
    """

    def setUp(self):
        super().setUp()
        # Populate every profile field a claim might draw from
        self.test_user.profile.website = "https://example.com/oauth_user"
        self.test_user.profile.save()

    def _userinfo(self, scope):
        """Hit the OIDC userinfo endpoint with a given scope and return the JSON."""
        self.access_token.scope = scope
        self.access_token.save()
        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get("/oauth/oidc/userinfo", HTTP_AUTHORIZATION=auth)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_profile_scope_returns_website(self):
        """The profile scope includes the optional website claim when set."""
        data = self._userinfo("openid profile")
        self.assertEqual(data["website"], "https://example.com/oauth_user")
        self.assertEqual(data["preferred_username"], self.test_user.username)

    def test_email_scope_returns_email_verified(self):
        """The email scope returns the email_verified claim alongside email."""
        data = self._userinfo("openid email")
        self.assertIn("email", data)
        self.assertIn("email_verified", data)
        self.assertIsInstance(data["email_verified"], bool)

    def test_institution_scope_returns_affiliation(self):
        """The institution:read scope returns the user's affiliation."""
        data = self._userinfo("openid institution:read")
        self.assertEqual(data["affiliation"], "MIT")

    def test_credentialing_scope_returns_credentialing_status(self):
        """The credentialing:read scope returns the user's credentialing status."""
        data = self._userinfo("openid credentialing:read")
        self.assertIn("is_credentialed", data)
        self.assertIsInstance(data["is_credentialed"], bool)

    def test_public_id_scope_returns_uuid(self):
        """The public_id:read scope returns the persistent public UUID."""
        data = self._userinfo("openid public_id:read")
        self.assertEqual(data["public_user_uuid"], str(self.test_user.public_user_uuid))

    def test_no_scope_returns_only_sub(self):
        """A token with no claim-bearing scopes still gets a sub claim."""
        data = self._userinfo("openid")
        self.assertEqual(data["sub"], str(self.test_user.public_user_uuid))
        self.assertNotIn("email", data)
        self.assertNotIn("affiliation", data)
        self.assertNotIn("name", data)


class TestOIDCProviderConfigValidation(TestCase):
    """
    Test that load_oidc_provider_config raises loudly on misconfiguration so
    the OIDC provider cannot silently fall back to a degraded state.
    """

    def _env(self, **values):
        """Return a get_env(name, default) callable backed by a static dict."""
        return lambda name, default='': values.get(name, default)

    def test_missing_key_file_raises(self):
        """A non-existent OIDC_RSA_KEY_FILE path raises ImproperlyConfigured."""
        with self.assertRaisesMessage(ImproperlyConfigured, 'no such file exists'):
            load_oidc_provider_config(self._env(
                OIDC_RSA_KEY_FILE='/nonexistent/oidc-key.pem',
                OIDC_ISS_ENDPOINT='https://example.org/oauth',
            ))

    def test_missing_inactive_key_file_raises(self):
        """A non-existent path in OIDC_RSA_INACTIVE_KEY_FILES raises ImproperlyConfigured."""
        with self.assertRaisesMessage(ImproperlyConfigured, 'OIDC_RSA_INACTIVE_KEY_FILES'):
            load_oidc_provider_config(self._env(
                OIDC_RSA_INACTIVE_KEY_FILES='/nonexistent/old-key.pem',
                OIDC_ISS_ENDPOINT='https://example.org/oauth',
            ))

    def test_missing_iss_endpoint_with_key_raises(self):
        """A signing key without OIDC_ISS_ENDPOINT raises ImproperlyConfigured."""
        with self.assertRaisesMessage(ImproperlyConfigured, 'OIDC_ISS_ENDPOINT'):
            load_oidc_provider_config(self._env(
                OIDC_RSA_PRIVATE_KEY='-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----',
                OIDC_ISS_ENDPOINT='',
            ))

    def test_no_key_returns_disabled_config(self):
        """With no key configured, OIDC is disabled and no validation fires."""
        cfg = load_oidc_provider_config(self._env())
        self.assertFalse(cfg['OIDC_ENABLED'])
        self.assertEqual(cfg['OIDC_RSA_PRIVATE_KEY'], '')
        self.assertEqual(cfg['OIDC_RSA_PRIVATE_KEYS_INACTIVE'], [])

    def test_inline_key_with_iss_returns_enabled_config(self):
        """An inline OIDC_RSA_PRIVATE_KEY with OIDC_ISS_ENDPOINT enables OIDC."""
        cfg = load_oidc_provider_config(self._env(
            OIDC_RSA_PRIVATE_KEY='inline-pem',
            OIDC_ISS_ENDPOINT='https://example.org/oauth',
        ))
        self.assertTrue(cfg['OIDC_ENABLED'])
        self.assertEqual(cfg['OIDC_RSA_PRIVATE_KEY'], 'inline-pem')
        self.assertEqual(cfg['OIDC_ISS_ENDPOINT'], 'https://example.org/oauth')

    def test_key_file_is_read_from_disk(self):
        """A valid OIDC_RSA_KEY_FILE is read and returned as the private key."""
        with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as f:
            f.write('contents-of-the-key-file')
            key_path = f.name
        try:
            cfg = load_oidc_provider_config(self._env(
                OIDC_RSA_KEY_FILE=key_path,
                OIDC_ISS_ENDPOINT='https://example.org/oauth',
            ))
            self.assertEqual(cfg['OIDC_RSA_PRIVATE_KEY'], 'contents-of-the-key-file')
        finally:
            os.unlink(key_path)

    def test_inactive_keys_are_loaded_in_order(self):
        """Each path in OIDC_RSA_INACTIVE_KEY_FILES is loaded into the inactive list."""
        with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as f1:
            f1.write('old-key-1')
            path1 = f1.name
        with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as f2:
            f2.write('old-key-2')
            path2 = f2.name
        try:
            cfg = load_oidc_provider_config(self._env(
                OIDC_RSA_PRIVATE_KEY='active',
                OIDC_RSA_INACTIVE_KEY_FILES=f'{path1},{path2}',
                OIDC_ISS_ENDPOINT='https://example.org/oauth',
            ))
            self.assertEqual(cfg['OIDC_RSA_PRIVATE_KEYS_INACTIVE'], ['old-key-1', 'old-key-2'])
        finally:
            os.unlink(path1)
            os.unlink(path2)


class TestGenerateOIDCRSAKeyCommand(TestCase):
    """
    Test the generate_oidc_rsa_key management command that operators run to
    create a signing key for the OIDC provider.
    """

    def test_writes_pkcs8_pem_to_stdout_by_default(self):
        """Without --output, the key is written to stdout in PKCS8 PEM format."""
        stdout = StringIO()
        stderr = StringIO()
        with mock.patch('sys.stdout.isatty', return_value=False):
            call_command('generate_oidc_rsa_key', stdout=stdout, stderr=stderr)
        pem = stdout.getvalue()
        self.assertIn('-----BEGIN PRIVATE KEY-----', pem)
        self.assertIn('-----END PRIVATE KEY-----', pem)
        # PKCS8-formatted RSA keys load successfully via cryptography
        serialization.load_pem_private_key(pem.encode(), password=None)

    def test_output_file_is_created_with_0600_permissions(self):
        """--output writes the key with restrictive 0600 permissions."""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'oidc.pem')
            call_command('generate_oidc_rsa_key', '--output', target)
            self.assertTrue(os.path.isfile(target))
            mode = os.stat(target).st_mode & 0o777
            self.assertEqual(mode, 0o600)
            with open(target) as f:
                self.assertIn('-----BEGIN PRIVATE KEY-----', f.read())

    def test_rejects_key_size_below_2048(self):
        """--bits below 2048 is rejected with an error to stderr."""
        stdout = StringIO()
        stderr = StringIO()
        call_command('generate_oidc_rsa_key', '--bits', '1024', stdout=stdout, stderr=stderr)
        self.assertIn('Key size must be at least 2048 bits', stderr.getvalue())
        self.assertEqual(stdout.getvalue(), '')


class TestCustomValidatorAdditionalClaims(OIDCBaseTest):
    """
    Test the validator-level helpers on CustomOAuth2Validator that don't
    have natural HTTP-level coverage.
    """

    def test_get_additional_claims_returns_empty_when_no_user(self):
        """get_additional_claims returns {} when the request has no user."""
        from oauth.validators import CustomOAuth2Validator
        validator = CustomOAuth2Validator()
        request = mock.MagicMock()
        request.user = None
        self.assertEqual(validator.get_additional_claims(request), {})


class TestTokenIntrospection(BaseTest):
    """
    Test the RFC 7662 token introspection endpoint at /oauth/introspect/.

    Resource servers POST an opaque access token plus their client credentials
    and learn whether the token is currently active and, if so, which scopes,
    user, and client it was issued for. Inactive (expired, revoked, unknown)
    tokens must surface as {"active": false} without leaking metadata, and
    requests with bad client credentials must be rejected outright.
    """

    def _post_introspect(self, token, client_id, client_secret):
        """Hit the introspection endpoint with HTTP Basic client auth."""
        auth_headers = self.get_basic_auth_header(client_id, client_secret)
        return self.client.post(
            reverse("oauth2_provider:introspect"),
            data={"token": token},
            **auth_headers,
        )

    def test_active_token_returns_claims(self):
        """An active token returns active=true with scope, client_id, username, exp."""
        response = self._post_introspect(
            self.access_token.token,
            self.application.client_id,
            CLEARTEXT_SECRET,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["active"])
        self.assertEqual(data["scope"], self.access_token.scope)
        self.assertEqual(data["client_id"], self.application.client_id)
        self.assertEqual(data["username"], self.test_user.username)
        self.assertIn("exp", data)

    def test_expired_token_returns_inactive(self):
        """An expired token introspects as active=false."""
        self.access_token.expires = timezone.now() - timedelta(hours=1)
        self.access_token.save()
        response = self._post_introspect(
            self.access_token.token,
            self.application.client_id,
            CLEARTEXT_SECRET,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["active"])

    def test_revoked_token_returns_inactive(self):
        """A deleted/revoked token introspects as active=false."""
        token_value = self.access_token.token
        self.access_token.delete()
        response = self._post_introspect(
            token_value,
            self.application.client_id,
            CLEARTEXT_SECRET,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["active"])

    def test_unknown_token_returns_inactive(self):
        """A token string that was never issued introspects as active=false."""
        response = self._post_introspect(
            "not-a-real-token-string",
            self.application.client_id,
            CLEARTEXT_SECRET,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["active"])

    def test_bad_client_credentials_are_rejected(self):
        """Wrong client secret is rejected, not silently downgraded."""
        # RFC 7662 calls for 401 + WWW-Authenticate, but DOT 2.2.0's
        # ClientProtectedResourceMixin.dispatch returns 403. Accept either
        # so we don't break on a DOT upgrade that brings this in line.
        response = self._post_introspect(
            self.access_token.token,
            self.application.client_id,
            "wrong-secret",
        )
        self.assertIn(response.status_code, (401, 403))


class TestApplicationsViewsRemoved(TestCase):
    """
    Regression test: the django-oauth-toolkit-shipped /oauth/applications/*
    views are not reachable. Operators manage Applications via the Console
    workflow (Stage C) and Django admin only.
    """

    def test_applications_list_is_404(self):
        """GET /oauth/applications/ returns 404."""
        response = self.client.get("/oauth/applications/")
        self.assertEqual(response.status_code, 404)

    def test_applications_register_is_404(self):
        """GET /oauth/applications/register/ returns 404."""
        response = self.client.get("/oauth/applications/register/")
        self.assertEqual(response.status_code, 404)


class TestPartnerModel(TestCase):
    """
    Test the Partner model that augments oauth2_provider.Application with
    organization metadata, scope allow-listing, post-logout redirect URIs,
    and a lifecycle status used by the Console partner-management workflow.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="partner_owner",
            email="partner_owner@example.com",
            password=get_random_string(20),
        )
        self.application = Application.objects.create(
            name="Acme App",
            redirect_uris="http://example.org",
            user=self.user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret=CLEARTEXT_SECRET,
        )

    def test_str_includes_org_name_and_client_id(self):
        """__str__ renders as 'organization_name (client_id)'."""
        partner = Partner.objects.create(
            application=self.application,
            organization_name="Acme",
            created_by=self.user,
        )
        self.assertEqual(str(partner), f"Acme ({self.application.client_id})")

    def test_status_defaults_to_active(self):
        """A newly created Partner has status=ACTIVE without explicit value."""
        partner = Partner.objects.create(
            application=self.application,
            organization_name="Acme",
            created_by=self.user,
        )
        self.assertEqual(partner.status, Partner.Status.ACTIVE)

    def test_is_legacy_property(self):
        """is_legacy is True iff organization_name starts with 'Legacy: '."""
        legacy = Partner.objects.create(
            application=self.application,
            organization_name=f"Legacy: {self.application.client_id}",
            created_by=self.user,
        )
        self.assertTrue(legacy.is_legacy)

        other_app = Application.objects.create(
            name="Acme App 2",
            redirect_uris="http://example.org",
            user=self.user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret=CLEARTEXT_SECRET,
        )
        normal = Partner.objects.create(
            application=other_app,
            organization_name="Acme",
            created_by=self.user,
        )
        self.assertFalse(normal.is_legacy)

    def test_cascade_delete_from_application(self):
        """Deleting the linked Application cascades to delete the Partner."""
        partner = Partner.objects.create(
            application=self.application,
            organization_name="Acme",
            created_by=self.user,
        )
        partner_pk = partner.pk
        self.application.delete()
        self.assertFalse(Partner.objects.filter(pk=partner_pk).exists())

    def test_allowed_scopes_round_trip(self):
        """allowed_scopes survives a save/refresh_from_db cycle intact."""
        partner = Partner.objects.create(
            application=self.application,
            organization_name="Acme",
            allowed_scopes=["openid", "profile", "email", "data:download"],
            created_by=self.user,
        )
        partner.refresh_from_db()
        self.assertEqual(
            partner.allowed_scopes,
            ["openid", "profile", "email", "data:download"],
        )

    def test_post_logout_redirect_uris_default_blank(self):
        """post_logout_redirect_uris defaults to an empty string."""
        partner = Partner.objects.create(
            application=self.application,
            organization_name="Acme",
            created_by=self.user,
        )
        self.assertEqual(partner.post_logout_redirect_uris, "")


class TestLegacyPartnerBackfill(TestCase):
    """
    Test the data-migration that creates 'Legacy: <client_id>' Partner rows
    for every Application present at deploy time. The migration runs as part
    of test database setup, so we just inspect the resulting state.
    """

    def setUp(self):
        super().setUp()
        # Create a fresh Application *after* migration has run, then verify
        # the backfill logic by re-running it on this row.
        self.user = User.objects.create_user(
            username="backfill_admin",
            email="backfill@example.com",
            password=get_random_string(20),
        )
        self.application = Application.objects.create(
            name="Pre-existing legacy app",
            redirect_uris="https://legacy.example.com/cb",
            user=self.user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        )

    def _backfill(self):
        """Import and call the data migration's backfill function."""
        import importlib
        from django.apps import apps as django_apps
        migration = importlib.import_module("oauth.migrations.0001_initial")
        migration.backfill_legacy_partners(django_apps, None)

    def test_backfill_creates_legacy_partner_for_application(self):
        """Running the backfill creates a Legacy Partner for an unattached Application."""
        self._backfill()
        partner = Partner.objects.get(application=self.application)
        self.assertTrue(partner.is_legacy)
        self.assertEqual(partner.organization_name, f"Legacy: {self.application.client_id}")
        self.assertEqual(partner.status, Partner.Status.ACTIVE)
        self.assertEqual(partner.allowed_scopes, [])
        self.assertIsNone(partner.created_by)

    def test_backfill_is_idempotent(self):
        """Running the backfill twice doesn't create duplicate Partners."""
        self._backfill()
        self._backfill()
        self.assertEqual(
            Partner.objects.filter(application=self.application).count(), 1,
        )


class TestPartnerAdmin(TestCase):
    """
    Smoke test that the Partner ModelAdmin is registered and gated behind
    Django's staff-access requirement.
    """

    def setUp(self):
        super().setUp()
        # The project's create_superuser sets is_admin only, not is_superuser,
        # so set is_superuser explicitly so /admin/ access is granted.
        self.staff_user = User.objects.create_user(
            username="staff_admin",
            email="staff@example.com",
            password=get_random_string(20),
            is_admin=True,
        )
        self.staff_user.is_superuser = True
        self.staff_user.save()

    def test_partner_admin_is_registered_and_reachable(self):
        """A staff user can access the Partner admin changelist."""
        self.client.force_login(self.staff_user)
        response = self.client.get("/admin/oauth/partner/")
        self.assertEqual(response.status_code, 200)

    def test_partner_admin_denied_to_anonymous(self):
        """Anonymous users are redirected to the admin login page."""
        response = self.client.get("/admin/oauth/partner/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])


class TestEndSessionView(OIDCBaseTest):
    """
    Test the OIDC RP-initiated logout endpoint at /oauth/end-session/.

    Validates that id_token_hint is verified against active and rotated-out
    signing keys, post_logout_redirect_uri is honoured only when registered
    on the issuing Partner, and the user's Django session is cleared in all
    cases (whether or not a redirect can be made).
    """

    END_SESSION_URL = "/oauth/end-session/"
    REGISTERED_REDIRECT = "https://acme.example.com/logged-out"

    def setUp(self):
        super().setUp()
        self.partner_owner = User.objects.create_user(
            username="end_session_owner",
            email="end_session_owner@example.com",
            password=get_random_string(20),
        )
        self.partner = Partner.objects.create(
            application=self.application,
            organization_name="Acme",
            post_logout_redirect_uris=self.REGISTERED_REDIRECT,
            created_by=self.partner_owner,
        )

    def _mint_jwt(self, pem, claims=None):
        """Sign a JWT with the given PEM key and default test claims."""
        payload = {
            "aud": self.application.client_id,
            "sub": str(self.test_user.public_user_uuid),
        }
        if claims:
            payload.update(claims)
        return jwt.encode(payload, pem, algorithm="RS256")

    def _login(self):
        """Log the test user in and assert the session was created."""
        self.assertTrue(
            self.client.login(username=self.test_user.username, password="123456")
        )
        self.assertIn("_auth_user_id", self.client.session)

    def test_valid_hint_and_registered_redirect_logs_out_and_redirects(self):
        """Valid hint + registered redirect logs the user out and 302s back."""
        token = self._mint_jwt(self.test_rsa_key_pem)
        self._login()
        response = self.client.get(
            self.END_SESSION_URL,
            data={
                "id_token_hint": token,
                "post_logout_redirect_uri": self.REGISTERED_REDIRECT,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.REGISTERED_REDIRECT)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unregistered_redirect_is_dropped(self):
        """Unregistered post_logout_redirect_uri is rejected; session still cleared."""
        token = self._mint_jwt(self.test_rsa_key_pem)
        self._login()
        response = self.client.get(
            self.END_SESSION_URL,
            data={
                "id_token_hint": token,
                "post_logout_redirect_uri": "https://evil.example.com/phish",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_no_hint_logs_out_and_renders_fallback(self):
        """With no params, the user is logged out and the fallback page renders."""
        self._login()
        response = self.client.get(self.END_SESSION_URL)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_forged_hint_is_rejected(self):
        """A hint signed by an unknown key cannot drive a redirect."""
        forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged_pem = forged_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        token = self._mint_jwt(forged_pem)
        self._login()
        response = self.client.get(
            self.END_SESSION_URL,
            data={
                "id_token_hint": token,
                "post_logout_redirect_uri": self.REGISTERED_REDIRECT,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_key_signed_hint_is_accepted(self):
        """A hint signed by a rotated-out (inactive) key still verifies."""
        old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        old_pem = old_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        token = self._mint_jwt(old_pem)
        rotation_settings = {
            **settings.OAUTH2_PROVIDER,
            "OIDC_RSA_PRIVATE_KEYS_INACTIVE": [old_pem],
        }
        with override_settings(OAUTH2_PROVIDER=rotation_settings):
            self._login()
            response = self.client.get(
                self.END_SESSION_URL,
                data={
                    "id_token_hint": token,
                    "post_logout_redirect_uri": self.REGISTERED_REDIRECT,
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.REGISTERED_REDIRECT)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_expired_hint_is_still_accepted_as_identity(self):
        """An expired hint is still honoured: it identifies who to log out."""
        token = self._mint_jwt(self.test_rsa_key_pem, claims={"exp": 0})
        self._login()
        response = self.client.get(
            self.END_SESSION_URL,
            data={
                "id_token_hint": token,
                "post_logout_redirect_uri": self.REGISTERED_REDIRECT,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.REGISTERED_REDIRECT)
        self.assertNotIn("_auth_user_id", self.client.session)


class TestPartnerScopeAndStatusEnforcement(BaseTest):
    """
    Test that CustomOAuth2Validator enforces per-partner scope allowlists
    and active/suspended/revoked status at /authorize, /token, and
    /introspect.
    """

    def setUp(self):
        super().setUp()
        from oauth.models import Partner
        self.partner = Partner.objects.create(
            application=self.application,
            organization_name="Acme",
            allowed_scopes=["openid", "profile", "email", "profile:read", "email:read"],
            created_by=self.dev_user,
        )

    def _try_authorize(self, scope, pkce=False):
        """Attempt the /authorize step and return the response."""
        self.client.login(username=self.test_user.username, password="123456")
        data = {
            "client_id": self.application.client_id,
            "state": "x",
            "scope": scope,
            "redirect_uri": "http://example.org",
            "response_type": "code",
            "allow": True,
        }
        non_pkce = {**settings.OAUTH2_PROVIDER, "PKCE_REQUIRED": False}
        with override_settings(OAUTH2_PROVIDER=non_pkce):
            return self.client.post(reverse("oauth2_provider:authorize"), data=data)

    def test_in_allowlist_scope_yields_code(self):
        """Requesting an in-allowlist scope returns an auth code."""
        response = self._try_authorize("openid profile")
        self.assertEqual(response.status_code, 302)
        self.assertIn("code=", response["Location"])

    def test_out_of_allowlist_scope_is_invalid_scope(self):
        """Requesting a scope not in allowed_scopes returns invalid_scope."""
        response = self._try_authorize("openid profile data:download")
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=invalid_scope", response["Location"])

    def test_wildcard_allowed_scopes_permits_any_global_scope(self):
        """Empty allowed_scopes is treated as wildcard (legacy compat)."""
        self.partner.allowed_scopes = []
        self.partner.save()
        response = self._try_authorize("openid profile data:download")
        self.assertEqual(response.status_code, 302)
        self.assertIn("code=", response["Location"])

    def test_suspended_partner_authorize_is_unauthorized_client(self):
        """A suspended partner is rejected at /authorize without consent screen.

        validate_client_id failure causes oauthlib to render an error page
        (HTTP 400) rather than redirect, since no redirect_uri can be trusted
        when the client_id itself is invalid.
        """
        from oauth.models import Partner
        self.partner.status = Partner.Status.SUSPENDED
        self.partner.save()
        response = self._try_authorize("openid")
        self.assertEqual(response.status_code, 400)

    def test_suspended_partner_token_exchange_returns_invalid_client(self):
        """An auth code obtained while active cannot be exchanged after suspension."""
        from oauth.models import Partner
        # First, get a code while active
        self.partner.status = Partner.Status.ACTIVE
        self.partner.save()
        response = self._try_authorize("openid")
        code = parse_qs(urlparse(response["Location"]).query)["code"][0]

        # Suspend the partner
        self.partner.status = Partner.Status.SUSPENDED
        self.partner.save()

        non_pkce = {**settings.OAUTH2_PROVIDER, "PKCE_REQUIRED": False}
        with override_settings(OAUTH2_PROVIDER=non_pkce):
            token_response = self.client.post(
                reverse("oauth2_provider:token"),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": "http://example.org",
                },
                **self.get_basic_auth_header(self.application.client_id, CLEARTEXT_SECRET),
            )
        self.assertEqual(token_response.status_code, 401)
        self.assertEqual(token_response.json()["error"], "invalid_client")

    def test_suspended_partner_cannot_introspect(self):
        """A suspended partner is rejected at /oauth/introspect/."""
        from oauth.models import Partner
        self.partner.status = Partner.Status.SUSPENDED
        self.partner.save()
        response = self.client.post(
            reverse("oauth2_provider:introspect"),
            data={"token": self.access_token.token},
            **self.get_basic_auth_header(self.application.client_id, CLEARTEXT_SECRET),
        )
        # DOT 2.2.0's ClientProtectedResourceMixin returns 403 on bad client auth
        self.assertIn(response.status_code, (401, 403))
