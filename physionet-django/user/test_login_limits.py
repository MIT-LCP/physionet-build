import base64

from django.core.cache import caches
from django.test import TestCase, override_settings
from django.urls import reverse

from user.models import User


def basic_auth(username, password):
    return 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()


@override_settings(LOGIN_FAILURE_LIMIT=3, LOGIN_FAILURE_CLIENT_LIMIT=5)
class LoginLimitTests(TestCase):
    def setUp(self):
        caches['login_failures'].clear()
        self.addCleanup(caches['login_failures'].clear)
        self.user = User.objects.create_user(
            email='login-limit@example.com', username='loginlimit',
            password='correct-password', is_active=True,
        )

    def login(self, password, username='loginlimit', client_address='127.0.0.1'):
        return self.client.post(reverse('login'), {'username': username, 'password': password},
                                REMOTE_ADDR=client_address)

    def test_login_is_refused_after_repeated_failures(self):
        for _ in range(2):
            response = self.login('wrong-password')
            self.assertContains(response, 'Please enter a correct username/email and password')
        # The failure that reaches the limit already explains it
        response = self.login('wrong-password')
        self.assertContains(response, 'Too many failed login attempts')
        response = self.login('correct-password')
        self.assertContains(response, 'Too many failed login attempts')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_counts_are_not_kept_in_the_default_cache(self):
        """Counts must be shared by every server process, unlike the per-process default cache."""
        for _ in range(3):
            self.login('wrong-password')
        caches['default'].clear()
        response = self.login('correct-password')
        self.assertContains(response, 'Too many failed login attempts')

    def test_other_clients_can_still_log_in(self):
        for _ in range(3):
            self.login('wrong-password')
        response = self.login('correct-password', client_address='192.0.2.10')
        self.assertEqual(response.status_code, 302)

    def test_successful_login_resets_the_account_count(self):
        for _ in range(2):
            self.login('wrong-password')
        self.assertEqual(self.login('correct-password').status_code, 302)
        self.client.logout()
        for _ in range(2):
            self.login('wrong-password')
        self.assertEqual(self.login('correct-password').status_code, 302)

    def test_client_is_limited_across_accounts(self):
        for index in range(5):
            self.login('wrong-password', username=f'unknown-user-{index}')
        response = self.login('correct-password')
        self.assertContains(response, 'Too many failed login attempts')

    def test_api_basic_auth_is_limited(self):
        url = reverse('published_project_versions', kwargs={'project_slug': 'demoeicu'})
        response = self.client.get(url, HTTP_AUTHORIZATION=basic_auth('loginlimit', 'correct-password'))
        self.assertEqual(response.status_code, 200)
        for _ in range(3):
            response = self.client.get(url, HTTP_AUTHORIZATION=basic_auth('loginlimit', 'wrong-password'))
            self.assertEqual(response.status_code, 401)
        response = self.client.get(url, HTTP_AUTHORIZATION=basic_auth('loginlimit', 'correct-password'))
        self.assertEqual(response.status_code, 401)
