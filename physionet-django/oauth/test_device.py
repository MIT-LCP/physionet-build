from datetime import timedelta
from urllib.parse import urlencode

from django.core.cache import caches
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import (
    get_access_token_model,
    get_application_model,
    get_device_grant_model,
    get_refresh_token_model,
)

from oauth.clients import PYTHON_CLIENT_ID, PYTHON_CLIENT_NAME, create_python_client
from oauth.user_codes import ALPHABET, format_user_code, generate_user_code
from user.models import User

AccessToken = get_access_token_model()
Application = get_application_model()
DeviceGrant = get_device_grant_model()
RefreshToken = get_refresh_token_model()

DEVICE_CODE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


class UserCodeTests(TestCase):
    def test_generated_codes_are_readable(self):
        code = generate_user_code()
        self.assertRegex(code, r"^[A-Z]{4}-[A-Z]{4}$")
        self.assertTrue(set(code.replace("-", "")) <= set(ALPHABET))

    def test_codes_can_be_typed_loosely(self):
        for typed in ["wdjb-mjht", "WDJBMJHT", " wdjb mjht "]:
            self.assertEqual(format_user_code(typed), "WDJB-MJHT")


class DeviceFlowTestBase(TestCase):
    def form_post(self, url, data):
        """POST as OAuth clients do, with a form-encoded body."""
        return self.client.post(url, data=urlencode(data), content_type="application/x-www-form-urlencoded")

    def setUp(self):
        caches["login_failures"].clear()
        create_python_client(Application)
        self.application = Application.objects.get(client_id=PYTHON_CLIENT_ID)
        self.user = User.objects.create_user(
            username="device_user", email="device_user@example.com", password="Tester11!", is_active=True
        )

    def start(self, **data):
        """Ask for a device code, as the Python package would."""
        data.setdefault("client_id", PYTHON_CLIENT_ID)
        return self.form_post(reverse("oauth2_provider:device-authorization"), data)

    def poll(self, device_code, client_id=PYTHON_CLIENT_ID):
        # Let the polling interval pass, so the server does not say slow down.
        DeviceGrant.objects.filter(device_code=device_code).update(
            last_checked=timezone.now() - timedelta(minutes=1)
        )
        return self.form_post(
            reverse("oauth2_provider:token"),
            {"grant_type": DEVICE_CODE_GRANT_TYPE, "device_code": device_code, "client_id": client_id},
        )

    def approve(self, user_code, action="accept"):
        """Enter the code and approve it, as the user would in a browser."""
        self.client.force_login(self.user)
        response = self.client.post(reverse("oauth2_provider:device"), data={"user_code": user_code})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(response["Location"], data={"action": action})
        self.assertEqual(response.status_code, 302)
        self.client.logout()
        return response


class DeviceFlowTests(DeviceFlowTestBase):
    def test_sign_in(self):
        response = self.start(scope="data:download")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        data = response.json()
        self.assertEqual(data["verification_uri"], "http://testserver/oauth/device/")
        self.assertRegex(data["user_code"], r"^[A-Z]{4}-[A-Z]{4}$")
        self.assertEqual(data["interval"], 5)

        response = self.poll(data["device_code"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "authorization_pending")

        # The user can type the code without the hyphen, in lower case
        self.approve(data["user_code"].replace("-", "").lower())

        response = self.poll(data["device_code"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        token = response.json()
        self.assertEqual(token["scope"], "data:download")
        self.assertIn("refresh_token", token)
        self.assertEqual(AccessToken.objects.get(user=self.user).application, self.application)

        # The code can only be exchanged once
        response = self.poll(data["device_code"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "expired_token")
        self.assertEqual(AccessToken.objects.filter(user=self.user).count(), 1)

        # The refresh token works
        response = self.form_post(
            reverse("oauth2_provider:token"),
            {"grant_type": "refresh_token", "refresh_token": token["refresh_token"], "client_id": PYTHON_CLIENT_ID},
        )
        self.assertEqual(response.status_code, 200)

    def test_default_scope_is_download_only(self):
        data = self.start().json()
        self.assertEqual(DeviceGrant.objects.get(device_code=data["device_code"]).scope, "data:download")

    def test_device_clients_can_only_ask_for_a_few_scopes(self):
        response = self.start(scope="data:download annotations:annotations:write")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_scope")

        response = self.start(scope="data:download profile:read")
        self.assertEqual(response.status_code, 200)

    def test_only_device_clients_can_start_a_device_sign_in(self):
        web_app = Application.objects.create(
            name="Web app", client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="https://example.com/callback",
        )
        before = DeviceGrant.objects.count()
        response = self.start(client_id=web_app.client_id, scope="data:download")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "unauthorized_client")
        self.assertEqual(DeviceGrant.objects.count(), before)

        response = self.start(client_id="no-such-client")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_description"], "Invalid client_id parameter value.")

    def test_bad_token_requests_get_oauth_errors(self):
        url = reverse("oauth2_provider:token")
        response = self.form_post(url, {"grant_type": DEVICE_CODE_GRANT_TYPE, "client_id": PYTHON_CLIENT_ID})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_request")

        response = self.form_post(url, {
            "grant_type": DEVICE_CODE_GRANT_TYPE, "device_code": "unknown", "client_id": PYTHON_CLIENT_ID})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_code_belongs_to_its_client(self):
        other = Application.objects.create(
            name="Other device app", client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_DEVICE_CODE,
        )
        data = self.start().json()
        self.approve(data["user_code"])
        response = self.poll(data["device_code"], client_id=other.client_id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_denied(self):
        data = self.start().json()
        self.approve(data["user_code"], action="deny")
        response = self.poll(data["device_code"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "access_denied")

    def test_expired(self):
        data = self.start().json()
        self.approve(data["user_code"])
        DeviceGrant.objects.filter(device_code=data["device_code"]).update(
            expires=timezone.now() - timedelta(seconds=1)
        )
        response = self.poll(data["device_code"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "expired_token")

    def test_expired_code_cannot_be_entered(self):
        data = self.start().json()
        DeviceGrant.objects.filter(device_code=data["device_code"]).update(
            expires=timezone.now() - timedelta(seconds=1)
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("oauth2_provider:device"), data={"user_code": data["user_code"]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Expired user code")

    def test_polling_too_fast(self):
        data = self.start().json()
        url = reverse("oauth2_provider:token")
        payload = {"grant_type": DEVICE_CODE_GRANT_TYPE, "device_code": data["device_code"],
                   "client_id": PYTHON_CLIENT_ID}
        response = self.form_post(url, payload)
        self.assertEqual(response.json()["error"], "slow_down")

    def test_deactivated_account_gets_no_token(self):
        data = self.start().json()
        self.approve(data["user_code"])
        User.objects.filter(id=self.user.id).update(is_active=False)
        response = self.poll(data["device_code"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_code_entry_needs_a_signed_in_user(self):
        response = self.client.get(reverse("oauth2_provider:device"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_confirm_page_explains_the_request(self):
        data = self.start().json()
        self.client.force_login(self.user)
        response = self.client.post(reverse("oauth2_provider:device"), data={"user_code": data["user_code"]})
        response = self.client.get(response["Location"])
        self.assertContains(response, PYTHON_CLIENT_NAME)
        self.assertContains(response, data["user_code"])
        self.assertContains(response, "Approve only if you started this sign-in yourself")

    def test_another_user_cannot_approve_a_code_someone_entered(self):
        data = self.start().json()
        self.client.force_login(self.user)
        response = self.client.post(reverse("oauth2_provider:device"), data={"user_code": data["user_code"]})
        confirm_url = response["Location"]

        other = User.objects.create_user(
            username="other_device_user", email="other_device_user@example.com", password="x", is_active=True
        )
        self.client.force_login(other)
        self.assertEqual(self.client.post(confirm_url, data={"action": "accept"}).status_code, 404)

    @override_settings(DEVICE_CODE_FAILURE_LIMIT=3)
    def test_wrong_codes_are_rate_limited(self):
        data = self.start().json()
        self.client.force_login(self.user)
        url = reverse("oauth2_provider:device")
        for _ in range(3):
            response = self.client.post(url, data={"user_code": "BBBB-BBBB"})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Incorrect user code")

        response = self.client.post(url, data={"user_code": data["user_code"]})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many incorrect codes", status_code=429)
        self.assertEqual(DeviceGrant.objects.get(device_code=data["device_code"]).user, None)


class DeviceFlowRaceTests(DeviceFlowTestBase):
    def enter(self, user_code, user=None):
        self.client.force_login(user or self.user)
        return self.client.post(reverse("oauth2_provider:device"), data={"user_code": user_code})

    def test_repeated_approval_cannot_reuse_a_code(self):
        data = self.start().json()
        confirm_url = self.enter(data["user_code"])["Location"]
        self.client.post(confirm_url, data={"action": "accept"})
        self.assertEqual(self.poll(data["device_code"]).status_code, 200)

        # A second "Approve" (such as a double click) arrives after the exchange
        response = self.client.post(confirm_url, data={"action": "accept"})
        self.assertEqual(response.status_code, 404)
        grant = DeviceGrant.objects.get(device_code=data["device_code"])
        grant_url = reverse("oauth2_provider:device-confirm", args=[grant.client_id, grant.user_code])
        self.assertEqual(grant.status, DeviceGrant.EXPIRED)

        # Even if the request gets past the lookup, the update is conditional
        from oauth.device import DeviceConfirmView
        view = DeviceConfirmView()
        view.setup(self.client.post(grant_url).wsgi_request, client_id=grant.client_id, user_code=grant.user_code)
        view._device_grant = grant
        form = view.get_form_class()(data={"action": "accept"})
        self.assertTrue(form.is_valid())
        view.form_valid(form)
        self.assertEqual(DeviceGrant.objects.get(pk=grant.pk).status, DeviceGrant.EXPIRED)
        self.assertEqual(self.poll(data["device_code"]).json()["error"], "expired_token")
        self.assertEqual(AccessToken.objects.filter(user=self.user).count(), 1)

    def test_deny_after_approval_does_not_change_the_decision(self):
        data = self.start().json()
        confirm_url = self.enter(data["user_code"])["Location"]
        self.client.post(confirm_url, data={"action": "accept"})
        grant = DeviceGrant.objects.get(device_code=data["device_code"])
        DeviceGrant.objects.filter(pk=grant.pk).update(status=DeviceGrant.AUTHORIZED)

        from oauth.device import DeviceConfirmView
        view = DeviceConfirmView()
        view.setup(self.client.post(confirm_url).wsgi_request, client_id=grant.client_id, user_code=grant.user_code)
        view._device_grant = grant
        form = view.get_form_class()(data={"action": "deny"})
        self.assertTrue(form.is_valid())
        view.form_valid(form)
        self.assertEqual(DeviceGrant.objects.get(pk=grant.pk).status, DeviceGrant.AUTHORIZED)

    def test_code_entered_by_one_user_cannot_be_claimed_by_another(self):
        data = self.start().json()
        self.enter(data["user_code"])
        other = User.objects.create_user(
            username="other_device_user", email="other_device_user@example.com", password="x", is_active=True
        )
        response = self.enter(data["user_code"], user=other)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User code has already been used")
        self.assertEqual(DeviceGrant.objects.get(device_code=data["device_code"]).user, self.user)

    @override_settings(DEVICE_AUTHORIZATION_CLIENT_LIMIT=2)
    def test_starting_sign_ins_is_rate_limited(self):
        before = DeviceGrant.objects.count()
        self.assertEqual(self.start().status_code, 200)
        self.assertEqual(self.start().status_code, 200)
        response = self.start()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"], "too_many_requests")
        self.assertEqual(DeviceGrant.objects.count(), before + 2)


class SignedInApplicationsTests(DeviceFlowTestBase):
    def sign_in(self):
        data = self.start().json()
        self.approve(data["user_code"])
        return self.poll(data["device_code"]).json()

    def test_listed_and_signed_out(self):
        token = self.sign_in()
        self.client.force_login(self.user)
        response = self.client.get(reverse("edit_tokens"))
        self.assertContains(response, PYTHON_CLIENT_NAME)

        response = self.client.post(reverse("edit_tokens"), data={
            "action": "sign_out_application", "application_id": str(self.application.id)})
        self.assertRedirects(response, reverse("edit_tokens"))
        self.assertFalse(AccessToken.objects.filter(user=self.user).exists())
        self.assertFalse(RefreshToken.objects.filter(user=self.user, revoked__isnull=True).exists())
        self.assertNotContains(self.client.get(reverse("edit_tokens")), PYTHON_CLIENT_NAME)

        # The refresh token no longer works
        self.client.logout()
        response = self.form_post(reverse("oauth2_provider:token"), {
            "grant_type": "refresh_token", "refresh_token": token["refresh_token"], "client_id": PYTHON_CLIENT_ID})
        self.assertEqual(response.status_code, 400)

    def test_sign_out_expires_approved_codes_not_yet_exchanged(self):
        self.sign_in()
        pending = self.start().json()
        self.approve(pending["user_code"])

        self.client.force_login(self.user)
        self.client.post(reverse("edit_tokens"), data={
            "action": "sign_out_application", "application_id": str(self.application.id)})
        self.client.logout()

        response = self.poll(pending["device_code"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "expired_token")
        self.assertFalse(AccessToken.objects.filter(user=self.user).exists())

    def test_cannot_sign_out_another_users_application(self):
        self.sign_in()
        other = User.objects.create_user(
            username="other_device_user", email="other_device_user@example.com", password="x", is_active=True
        )
        self.client.force_login(other)
        self.client.post(reverse("edit_tokens"), data={
            "action": "sign_out_application", "application_id": str(self.application.id)})
        self.assertTrue(AccessToken.objects.filter(user=self.user).exists())


class DeviceGrantCleanupTests(DeviceFlowTestBase):
    def test_starting_a_sign_in_deletes_expired_codes(self):
        old = self.start().json()
        recent = self.start().json()
        DeviceGrant.objects.filter(device_code=old["device_code"]).update(
            expires=timezone.now() - timedelta(minutes=11)
        )
        DeviceGrant.objects.filter(device_code=recent["device_code"]).update(
            expires=timezone.now() - timedelta(minutes=1)
        )
        self.start()
        self.assertFalse(DeviceGrant.objects.filter(device_code=old["device_code"]).exists())
        # Recently expired codes are kept, so a polling client is told they expired
        self.assertEqual(self.poll(recent["device_code"]).json()["error"], "expired_token")

    def test_old_device_codes_are_deleted(self):
        old = self.start().json()
        new = self.start().json()
        DeviceGrant.objects.filter(device_code=old["device_code"]).update(
            expires=timezone.now() - timedelta(days=2)
        )
        call_command("purge_expired_access_tokens")
        self.assertFalse(DeviceGrant.objects.filter(device_code=old["device_code"]).exists())
        self.assertTrue(DeviceGrant.objects.filter(device_code=new["device_code"]).exists())
