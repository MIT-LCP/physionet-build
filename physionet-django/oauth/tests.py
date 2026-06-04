import base64
import hashlib
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from user.models import User
from oauth2_provider.models import get_access_token_model, get_application_model
from django.urls import reverse
from urllib.parse import parse_qs, urlparse
from oauth2_provider.settings import oauth2_settings
from django.utils.crypto import get_random_string
from oauth.views import SCOPES_MAPPING
from project.models import PublishedProject, AccessPolicy, CoreProject, ProjectType
from unittest.mock import patch


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


class TestDatasetAccessView(BaseTest):
    """
    Tests for GET /oauth/dataset-access/

    The endpoint requires the ``credentialing:read`` scope and accepts
    ``?slug=<slug>&version=<version>`` query parameters.  It delegates
    access-checking to ``project.authorization.access.can_access_project``,
    so the tests mock that function rather than reproducing the full
    DUA / credentialing process.
    """

    def setUp(self):
        super().setUp()

        self.open_project = PublishedProject.objects.create(
            slug="demoeicu",
            version="1.0",
            title="Demo Open Dataset",
            access_policy=AccessPolicy.OPEN,
            resource_type=ProjectType.objects.get(id=0),
            submission_slug="demoeicu",
            core_project=CoreProject.objects.create(),
        )
        self.credentialed_project = PublishedProject.objects.create(
            slug="mimiciv",
            version="3.1",
            title="MIMIC-IV",
            access_policy=AccessPolicy.CREDENTIALED,
            resource_type=ProjectType.objects.get(id=0),
            submission_slug="mimiciv",
            core_project=CoreProject.objects.create(),
        )

        self.credentialing_token = AccessToken.objects.create(
            user=self.test_user,
            scope="credentialing:read",
            expires=timezone.now() + timedelta(seconds=300),
            token="credentialing-token-key",
            application=self.application,
        )

    # Authentication
    def test_no_token_returns_403(self):
        response = self.client.get(
            "/oauth/dataset-access/", {"slug": "demoeicu", "version": "1.0"}
        )
        self.assertEqual(response.status_code, 403)

    def test_wrong_scope_returns_403(self):
        """A token with only profile:read must be rejected (needs credentialing:read)."""
        auth = self._create_authorization_header(self.access_token.token)
        response = self.client.get(
            "/oauth/dataset-access/",
            {"slug": "demoeicu", "version": "1.0"},
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, 403)

    # Parameter validation
    def test_missing_slug_returns_400(self):
        auth = self._create_authorization_header(self.credentialing_token.token)
        response = self.client.get(
            "/oauth/dataset-access/", {"version": "1.0"}, HTTP_AUTHORIZATION=auth
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_missing_version_returns_400(self):
        auth = self._create_authorization_header(self.credentialing_token.token)
        response = self.client.get(
            "/oauth/dataset-access/", {"slug": "demoeicu"}, HTTP_AUTHORIZATION=auth
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    # Project lookup
    def test_nonexistent_project_returns_404(self):
        auth = self._create_authorization_header(self.credentialing_token.token)
        response = self.client.get(
            "/oauth/dataset-access/",
            {"slug": "does-not-exist", "version": "9.9"},
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["has_access"])

    # Access checks — mock can_access_project
    def test_open_project_user_has_access(self):
        auth = self._create_authorization_header(self.credentialing_token.token)
        with patch("oauth.views.can_access_project", return_value=True):
            response = self.client.get(
                "/oauth/dataset-access/",
                {"slug": "demoeicu", "version": "1.0"},
                HTTP_AUTHORIZATION=auth,
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["has_access"])
        self.assertEqual(data["slug"], "demoeicu")
        self.assertEqual(data["version"], "1.0")

    def test_credentialed_project_access_denied(self):
        auth = self._create_authorization_header(self.credentialing_token.token)
        with patch("oauth.views.can_access_project", return_value=False):
            response = self.client.get(
                "/oauth/dataset-access/",
                {"slug": "mimiciv", "version": "3.1"},
                HTTP_AUTHORIZATION=auth,
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["has_access"])

    def test_response_echoes_slug_and_version(self):
        auth = self._create_authorization_header(self.credentialing_token.token)
        with patch("oauth.views.can_access_project", return_value=True):
            response = self.client.get(
                "/oauth/dataset-access/",
                {"slug": "mimiciv", "version": "3.1"},
                HTTP_AUTHORIZATION=auth,
            )

        data = response.json()
        self.assertEqual(data["slug"], "mimiciv")
        self.assertEqual(data["version"], "3.1")
