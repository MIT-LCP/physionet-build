from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from user.models import AccessToken, User


class TestAccessTokens(TestCase):
    def setUp(self):
        self.user = User.objects.get(email="admin@mit.edu")
        self.client.login(username="admin@mit.edu", password="Tester11!")

    def test_token_settings_page_renders(self):
        response = self.client.get(reverse("edit_tokens"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API Access Tokens")

    def test_create_token_with_fixed_60_day_expiration(self):
        response = self.client.post(reverse("edit_tokens"), data={"name": "Fixed Expiry Token"})
        self.assertRedirects(response, reverse("edit_tokens"))

        token = AccessToken.objects.get(user=self.user, name="Fixed Expiry Token")
        self.assertIsNotNone(token.expires_at)

        expected_expiration = token.created + timedelta(days=60)
        delta = abs(token.expires_at - expected_expiration)
        self.assertLess(delta.total_seconds(), 5)

    def test_token_expiration_logic(self):
        expired_token = AccessToken.objects.create(
            user=self.user,
            name="Old Token",
            expires_at=timezone.now() - timedelta(days=1)
        )
        self.assertTrue(expired_token.is_expired())

    def test_token_deletion(self):
        token = AccessToken.objects.create(
            user=self.user,
            name="Temporary",
            expires_at=timezone.now() + timedelta(days=60)
        )
        response = self.client.get(reverse("edit_tokens") + f"?delete={token.id}")
        self.assertRedirects(response, reverse("edit_tokens"))
        self.assertFalse(AccessToken.objects.filter(id=token.id).exists())
