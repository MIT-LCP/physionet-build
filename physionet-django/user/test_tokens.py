from datetime import timedelta

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from oauth2_provider.models import get_access_token_model, get_application_model

from django.utils.crypto import get_random_string

AccessToken = get_access_token_model()
Application = get_application_model()
User = get_user_model()


class TestAccessTokens(TestCase):
    def setUp(self):
        self.user = User.objects.get(email="admin@mit.edu")
        self.client.login(username="admin@mit.edu", password="Tester11!")

        Application = get_application_model()
        self.application = Application.objects.get(name=settings.OAUTH_CLIENT_APP_NAME)

    def test_token_settings_page_renders(self):
        response = self.client.get(reverse("edit_tokens"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API Access Tokens")

    def test_create_token_with_fixed_60_day_expiration(self):
        response = self.client.post(reverse("edit_tokens"), data={"name": "Fixed Expiry Token"})
        self.assertRedirects(response, reverse("edit_tokens"))

        token = AccessToken.objects.filter(user=self.user, application=self.application).latest("created")
        self.assertIsNotNone(token.expires)

        expected_expiration = token.created + timedelta(days=60)
        delta = abs(token.expires - expected_expiration)
        self.assertLess(delta.total_seconds(), 5)

    def test_token_expiration_logic(self):
        expired_token = AccessToken.objects.create(
            user=self.user,
            application=self.application,
            token=get_random_string(40),
            expires=timezone.now() - timedelta(days=1),
            scope="read",
        )
        self.assertTrue(expired_token.is_expired())

    def test_token_deletion(self):
        token = AccessToken.objects.create(
            user=self.user,
            application=self.application,
            token=get_random_string(40),
            expires=timezone.now() + timedelta(days=60),
            scope="read",
        )
        response = self.client.get(reverse("edit_tokens") + f"?delete={token.id}")
        self.assertRedirects(response, reverse("edit_tokens"))
        self.assertFalse(AccessToken.objects.filter(id=token.id).exists())

    def test_token_generation(self):
        # Reset tokens
        AccessToken.objects.filter(user=self.user, application=self.application).delete()

        self.client.login(username='admin@mit.edu', password='Tester11!')
        user = User.objects.get(email='admin@mit.edu')

        # Visit the token settings page (GET)
        response = self.client.get(reverse('edit_tokens'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API Access Tokens")

        # Create a new token (POST)
        response = self.client.post(reverse('edit_tokens'), data={'name': 'Test Token'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('edit_tokens'))

        # Verify that token exists in DB
        tokens = AccessToken.objects.filter(user=user)
        self.assertEqual(tokens.count(), 1)
        self.assertTrue(len(tokens.first().token) >= 32)

    def test_token_limit_enforced(self):
        """
        Users are limited to 3 tokens at a time.
        """
        AccessToken.objects.filter(user=self.user, application=self.application).delete()
        for i in range(3):
            AccessToken.objects.create(
                user=self.user,
                application=self.application,
                token=f"token-{i}",
                expires=timezone.now() + timedelta(days=60),
                scope="data:download",
            )

        response = self.client.post(reverse("edit_tokens"),
                                    data={"name": "Should Fail"}, follow=True)
        self.assertContains(response, "You can only have up to 3 tokens")
