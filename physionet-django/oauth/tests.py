from django.test import TestCase
from user.models import User
from oauth2_provider.models import get_application_model, AccessToken
from django.utils import timezone
from datetime import timedelta

Application = get_application_model()

class OAuthTestCase(TestCase):
    def setUp(self):
        self.test_user = User.objects.create_user("test_user", "test@user.com", "123456")
        self.application = Application.objects.create(
            name="Test Application",
            redirect_uris="http://localhost:8000/oauth/hello/",
            user=self.test_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        )

def test_authorize(self):
    # Set up test data
    query_params = {
        'client_id': self.application.client_id,
        'response_type': 'code',
        'state': 'random_state_string',
        'redirect_uri': self.application.redirect_uris,
    }

    # Log in the test user
    self.client.login(username='test_user', password='123456')

    # Make a GET request to the authorize endpoint with the query parameters
    response = self.client.get('/oauth/authorize/', data=query_params)

    # Assert that the response status code is 200 (OK)
    self.assertEqual(response.status_code, 200)

def test_token(self):
    # Set up test data
    token = AccessToken.objects.create(
        user=self.test_user,
        token='1234567890',
        application=self.application,
        scope='read write',
        expires=timezone.now() + timedelta(days=1)
    )
    auth_headers = {
        'HTTP_AUTHORIZATION': 'Bearer ' + token.token,
    }

    # Make a GET request to the token endpoint with the authorization headers
    response = self.client.get('/oauth/token/', **auth_headers)

    # Assert that the response status code is 200 (OK)
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()['access_token'], token.token)
