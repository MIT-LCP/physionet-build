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
            scope="read write",
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
            "scope": "read write",
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
            "scope": "read write",
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
