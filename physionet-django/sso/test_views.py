from django.conf import settings
from django.conf.urls import include
from django.test import TestCase, override_settings
from django.urls import path, reverse
from physionet.urls import urlpatterns
from unittest import skipIf
from user.models import User

authentication_backends = settings.AUTHENTICATION_BACKENDS + ['sso.auth.RemoteUserBackend']

@override_settings(AUTHENTICATION_BACKENDS=authentication_backends)
@skipIf(not settings.ENABLE_SSO, "SSO urls are disabled")
class TestViews(TestCase):
    def setUp(self):
        urlpatterns.append(path('', include('sso.urls')))
        self.inactive_user = User.objects.create(
            username='sso_inactive', email='sso_inactive@mit.edu', sso_id='inactive_remote_id'
        )
        self.active_user = User.objects.create(
            username='sso_active', email='sso_active@mit.edu', sso_id='active_remote_id', is_active=True
        )

    def tearDown(self):
        del urlpatterns[-1]

    def assertNotAuthenticated(self):
        self.assertNotIn('_auth_user_id', self.client.session)

    def assertAuthenticatedAs(self, user):
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session['_auth_user_id'], str(user.id))

    def test_login_authenticated(self):
        self.client.login(remote_user=self.active_user.sso_id)
        response = self.client.get(reverse('sso_login'))
        self.assertRedirects(response, reverse('project_home'))
        self.assertAuthenticatedAs(self.active_user)

    def test_login_no_remote_user(self):
        response = self.client.get(reverse('sso_login'))
        self.assertRedirects(response, reverse('home'))
        self.assertNotAuthenticated()

    def test_login_new(self):
        response = self.client.get(reverse('sso_login'), REMOTE_USER='new_remote_id')
        self.assertRedirects(response, reverse('sso_register'), fetch_redirect_response=False)
        self.assertNotAuthenticated()

    def test_login_inactive(self):
        response = self.client.get(reverse('sso_login'), REMOTE_USER=self.inactive_user.sso_id)
        self.assertRedirects(response, reverse('sso_register'), fetch_redirect_response=False)
        self.assertNotAuthenticated()

    def test_login_active(self):
        response = self.client.get(reverse('sso_login'), REMOTE_USER=self.active_user.sso_id)
        self.assertRedirects(response, reverse('project_home'))
        self.assertAuthenticatedAs(self.active_user)
