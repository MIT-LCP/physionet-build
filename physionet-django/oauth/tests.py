from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from user.models import User
from oauth2_provider.models import get_access_token_model, get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()


class TestOAuth2Authentication(TestCase):
    def setUp(self):
        """
        Create a demo user, an OAuth Application and an access token for use in testing.
        """
        self.test_user = User.objects.create_user("oauth_test_user", "oauth_test@example.com", "123456")
        self.application = Application.objects.create(
            name="Test Application",
            redirect_uris="http://localhost http://example.com http://example.org",
            user=self.test_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
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
