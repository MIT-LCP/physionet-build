from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import get_access_token_model, get_application_model
from rest_framework.test import APIClient

from user.management.commands.purge_expired_access_tokens import EXPIRED_TOKEN_DAY_LIMIT
from user.models import PersonalAccessToken

AccessToken = get_access_token_model()
Application = get_application_model()
User = get_user_model()

COLLECTION_WRITE = "annotations:collections:write"


class TokenSettingsPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.get(email="admin@mit.edu")
        self.client.login(username="admin@mit.edu", password="Tester11!")
        PersonalAccessToken.objects.filter(user=self.user).delete()

    def create(self, endpoints=("annotations/collections/write",)):
        return self.client.post(
            reverse("edit_tokens"), data={"action": "create", "annotation_endpoints": list(endpoints)}
        )

    def test_page_renders(self):
        response = self.client.get(reverse("edit_tokens"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API Access Tokens")

    def test_new_token_is_shown_once_and_only_its_hash_is_stored(self):
        response = self.create()

        self.assertEqual(response.status_code, 200)
        token = response.context["new_token"]
        self.assertTrue(token.startswith("pnpat_"))
        self.assertEqual(len(token), len("pnpat_") + PersonalAccessToken.RANDOM_LENGTH)
        self.assertContains(response, token)
        self.assertEqual(response["Cache-Control"], "no-store")

        record = PersonalAccessToken.objects.get(user=self.user)
        self.assertEqual(record.token_hash, PersonalAccessToken.hash_token(token))
        self.assertNotIn(token, [record.token_hash, record.display_prefix, record.scope])
        self.assertEqual(record.display_prefix, token[:PersonalAccessToken.DISPLAY_LENGTH])
        self.assertEqual(record.scopes, {COLLECTION_WRITE})

        later = self.client.get(reverse("edit_tokens"))
        self.assertNotContains(later, token)
        self.assertContains(later, record.display_prefix)

    def test_token_expires_after_its_lifetime(self):
        self.create()
        record = PersonalAccessToken.objects.get(user=self.user)
        delta = record.expires - (record.created + PersonalAccessToken.LIFETIME)
        self.assertLess(abs(delta.total_seconds()), 5)

    def test_token_needs_a_known_scope(self):
        for endpoints in [(), ("not/a/real/endpoint",)]:
            response = self.create(endpoints)
            self.assertRedirects(response, reverse("edit_tokens"))
        self.assertFalse(PersonalAccessToken.objects.filter(user=self.user).exists())

    def test_limit_counts_only_active_tokens(self):
        for _ in range(PersonalAccessToken.MAX_ACTIVE_PER_USER):
            record, _ = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
            record.expires = timezone.now() - timedelta(days=1)
            record.save()
        self.assertEqual(self.create().status_code, 200)

        for _ in range(PersonalAccessToken.MAX_ACTIVE_PER_USER - 1):
            PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        response = self.create()
        self.assertRedirects(response, reverse("edit_tokens"))
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("up to 3 active tokens" in m for m in messages))
        self.assertEqual(PersonalAccessToken.active().filter(user=self.user).count(), 3)

    def test_revoke_with_post(self):
        record, _ = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        response = self.client.post(
            reverse("edit_tokens"), data={"action": "revoke", "token_id": str(record.id)}
        )
        self.assertRedirects(response, reverse("edit_tokens"))
        self.assertFalse(PersonalAccessToken.objects.filter(id=record.id).exists())

    def test_get_request_cannot_revoke(self):
        record, _ = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        self.client.get(reverse("edit_tokens") + f"?delete={record.id}")
        self.assertTrue(PersonalAccessToken.objects.filter(id=record.id).exists())

    def test_revoke_and_create_require_csrf_token(self):
        record, _ = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        client = Client(enforce_csrf_checks=True)
        client.login(username="admin@mit.edu", password="Tester11!")
        for data in [
            {"action": "revoke", "token_id": str(record.id)},
            {"action": "create", "annotation_endpoints": ["annotations/collections/write"]},
        ]:
            self.assertEqual(client.post(reverse("edit_tokens"), data=data).status_code, 403)
        self.assertEqual(list(PersonalAccessToken.objects.filter(user=self.user)), [record])

    def test_cannot_revoke_another_users_token(self):
        other = User.objects.exclude(id=self.user.id).first()
        record, _ = PersonalAccessToken.create_for_user(other, [COLLECTION_WRITE])
        self.client.post(reverse("edit_tokens"), data={"action": "revoke", "token_id": str(record.id)})
        self.assertTrue(PersonalAccessToken.objects.filter(id=record.id).exists())

    def test_page_does_not_need_an_oauth_application(self):
        with self.settings(OAUTH_CLIENT_APP_NAME=""):
            self.assertEqual(self.client.get(reverse("edit_tokens")).status_code, 200)
            self.assertEqual(self.create().status_code, 200)


class TokenAPITests(TestCase):
    """Personal access tokens on the annotation API, which opts in to tokens."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="token_api_user", email="token_api@example.com", password="123456", is_active=True
        )
        self.client = APIClient()

    def create_collection(self, token):
        return self.client.post(
            reverse("annotation:annotation-collection-create"),
            data={"slug": "token-collection", "name": "Token collection", "description": "From a token"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_token_with_the_right_scope_is_accepted_and_use_is_recorded(self):
        record, token = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        response = self.create_collection(token)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["created_by"], self.user.id)
        record.refresh_from_db()
        self.assertIsNotNone(record.last_used)

    def test_token_without_the_scope_is_refused(self):
        _, token = PersonalAccessToken.create_for_user(self.user, ["annotations:collections:read"])
        self.assertEqual(self.create_collection(token).status_code, 403)

    def test_invalid_tokens_are_refused(self):
        expired, expired_token = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        expired.expires = timezone.now() - timedelta(seconds=1)
        expired.save()
        revoked, revoked_token = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        revoked.delete()

        for token in [expired_token, revoked_token, "pnpat_" + "x" * PersonalAccessToken.RANDOM_LENGTH]:
            response = self.create_collection(token)
            self.assertEqual(response.status_code, 401, token)
            self.assertEqual(response["WWW-Authenticate"], 'Bearer realm="api"')

    def test_tokens_of_deactivated_accounts_are_refused(self):
        _, token = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.create_collection(token).status_code, 401)

    def test_token_access_is_opt_in_per_view(self):
        """
        OAuth tokens are not a default way to authenticate API views, and
        personal tokens are accepted only by views that list them, so
        the SHA256SUMS endpoint (OAuth tokens with the download scope only)
        does not accept a personal token.
        """
        self.assertNotIn(
            "oauth2_provider.contrib.rest_framework.OAuth2Authentication",
            settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
        )
        _, personal_token = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        url = reverse("published_project_sha256sums", args=["demobsn", "1.0"])
        response = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {personal_token}")
        self.assertEqual(response.status_code, 401)

    def test_oauth_tokens_do_not_log_in_to_site_pages(self):
        """
        An OAuth token, such as one issued to a "Sign in with PhysioNet" app,
        must not act as a login on pages, whatever its scopes.
        """
        application = Application.objects.create(
            name="Token API test client",
            user=self.user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="http://localhost",
        )
        oauth_token = AccessToken.objects.create(
            user=self.user, application=application, token="openid-only-token",
            scope="openid", expires=timezone.now() + timedelta(minutes=5),
        )
        _, personal_token = PersonalAccessToken.create_for_user(self.user, [COLLECTION_WRITE])
        for token in [oauth_token.token, personal_token]:
            response = Client().get(reverse("edit_profile"), HTTP_AUTHORIZATION=f"Bearer {token}")
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response["Location"].startswith(settings.LOGIN_URL))


class ExpiredTokenCleanupTests(TestCase):
    def test_tokens_expired_beyond_the_limit_are_deleted(self):
        user = User.objects.get(email="admin@mit.edu")
        PersonalAccessToken.objects.all().delete()
        keep_active, _ = PersonalAccessToken.create_for_user(user, [COLLECTION_WRITE])
        keep_recent, _ = PersonalAccessToken.create_for_user(user, [COLLECTION_WRITE])
        remove_old, _ = PersonalAccessToken.create_for_user(user, [COLLECTION_WRITE])
        keep_recent.expires = timezone.now() - timedelta(days=1)
        keep_recent.save()
        remove_old.expires = timezone.now() - timedelta(days=EXPIRED_TOKEN_DAY_LIMIT + 1)
        remove_old.save()

        call_command("purge_expired_access_tokens")

        self.assertEqual(
            set(PersonalAccessToken.objects.values_list("id", flat=True)), {keep_active.id, keep_recent.id}
        )
