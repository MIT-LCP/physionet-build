import re

from django.conf import settings
from django.conf.urls import include
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import path, reverse
from physionet.urls import urlpatterns
from user.models import Profile, User

authentication_backends = settings.AUTHENTICATION_BACKENDS + ['sso.auth.RemoteUserBackend']

installed_apps = settings.INSTALLED_APPS + ['sso']


@override_settings(
    AUTHENTICATION_BACKENDS=authentication_backends,
    INSTALLED_APPS=installed_apps,
    ROOT_URLCONF='sso.tests.urls',
    ENABLE_SSO=True
)
class TestViews(TestCase):
    def setUp(self):

        # needs to insert it before the catchall url
        urlpatterns.insert(-1, path('', include('sso.urls')))
        self.inactive_user = User.objects.create(
            username='ssoinactive', email='sso_inactive@mit.edu', sso_id='inactive_remote_id'
        )
        Profile.objects.create(
            user=self.inactive_user, first_names='sso', last_name='inactive'
        )
        self.active_user = User.objects.create(
            username='ssoactive', email='sso_active@mit.edu', sso_id='active_remote_id', is_active=True
        )
        Profile.objects.create(
            user=self.active_user, first_names='sso', last_name='active'
        )

    def tearDown(self):
        del urlpatterns[-1]

    def assertNotAuthenticated(self):
        self.assertNotIn('_auth_user_id', self.client.session)

    def assertAuthenticatedAs(self, user):
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session['_auth_user_id'], str(user.id))

    def getActivationUrl(self):
        return re.findall(
            'http://localhost:8000/sso/activate/'
            '(?P<uidb64>[0-9A-Za-z_-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/',
            mail.outbox[0].body,
        )[0]

    def test_login_authenticated(self):
        self.client.login(remote_user=self.active_user.sso_id)
        response = self.client.get(reverse('sso_login'), HTTP_REMOTE_USER=self.active_user.sso_id)
        self.assertRedirects(response, reverse('project_home'))
        self.assertAuthenticatedAs(self.active_user)

    def test_login_no_remote_user(self):
        response = self.client.get(reverse('sso_login'))
        self.assertRedirects(response, reverse('login'))
        self.assertNotAuthenticated()

    def test_login_new(self):
        response = self.client.get(reverse('sso_login'), HTTP_REMOTE_USER='new_remote_id')
        self.assertRedirects(response, reverse('sso_register'), fetch_redirect_response=False)
        self.assertNotAuthenticated()

    def test_login_inactive(self):
        response = self.client.get(reverse('sso_login'), HTTP_REMOTE_USER=self.inactive_user.sso_id)
        self.assertRedirects(response, reverse('sso_register'), fetch_redirect_response=False)
        self.assertNotAuthenticated()

    def test_login_active(self):
        response = self.client.get(reverse('sso_login'), HTTP_REMOTE_USER=self.active_user.sso_id)
        self.assertRedirects(response, reverse('project_home'))
        self.assertAuthenticatedAs(self.active_user)

    def test_register_authenticated(self):
        self.client.login(remote_user=self.active_user.sso_id)
        response = self.client.get(reverse('sso_register'))
        self.assertRedirects(response, reverse('project_home'))
        self.assertAuthenticatedAs(self.active_user)

    def test_register_no_remote_user(self):
        response = self.client.get(reverse('sso_register'))
        self.assertRedirects(response, reverse('login'))
        self.assertNotAuthenticated()

    def test_sso_register_new(self):
        # GET registration page
        response = self.client.get(reverse('sso_register'), HTTP_REMOTE_USER='new_remote_id')
        self.assertEqual(response.status_code, 200)
        self.assertNotAuthenticated()

        # POST registration form
        data = {
            'email': 'sso_new@mit.edu', 'username': 'ssonew', 'first_names': 'SSO', 'last_name': 'New',
            'privacy_policy': 'True'
        }
        response = self.client.post(reverse('sso_register'), data=data, HTTP_REMOTE_USER='new_remote_id')
        self.assertEqual(response.status_code, 200)
        new_user = User.objects.get(sso_id='new_remote_id')
        self.assertFalse(new_user.is_active)
        self.assertEqual(new_user.email, 'sso_new@mit.edu')
        self.assertEqual(new_user.username, 'ssonew')
        self.assertEqual(new_user.profile.first_names, 'SSO')
        self.assertEqual(new_user.profile.last_name, 'New')
        self.assertNotAuthenticated()

    def test_sso_register_inactive(self):
        response = self.client.get(reverse('sso_register'), HTTP_REMOTE_USER=self.inactive_user.sso_id)
        self.assertEqual(response.status_code, 200)
        self.assertNotAuthenticated()

    def test_sso_register_active(self):
        response = self.client.get(reverse('sso_register'), HTTP_REMOTE_USER=self.active_user.sso_id)
        self.assertRedirects(response, reverse('sso_login'), fetch_redirect_response=False)
        self.assertNotAuthenticated()

    def test_sso_activate_user_invalid(self):
        # POST registration form
        data = {
            'email': 'sso_new@mit.edu', 'username': 'ssonew', 'first_names': 'SSO', 'last_name': 'New',
            'privacy_policy': 'True'
        }
        response = self.client.post(reverse('sso_register'), data=data, HTTP_REMOTE_USER='new_remote_id')

        # GET activation page without REMOTE USER
        uidb64, token = self.getActivationUrl()
        response = self.client.get(reverse('sso_activate_user', args=(uidb64, token)))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid Activation Link', response.content)
        new_user = User.objects.get(sso_id='new_remote_id')
        self.assertFalse(new_user.is_active)
        self.assertNotAuthenticated()

        # GET activation page with invalid uidb64
        response = self.client.get(
            reverse('sso_activate_user', args=('invaliduidb64', token)), HTTP_REMOTE_USER='new_remote_id'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid Activation Link', response.content)
        new_user = User.objects.get(sso_id='new_remote_id')
        self.assertFalse(new_user.is_active)
        self.assertNotAuthenticated()

        # GET activation page with invalid token
        invalid_token = 'a' * 8 + '-' + 'b' * 13
        response = self.client.get(
            reverse('sso_activate_user', args=(uidb64, invalid_token)), HTTP_REMOTE_USER='new_remote_id'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid Activation Link', response.content)
        new_user = User.objects.get(sso_id='new_remote_id')
        self.assertFalse(new_user.is_active)
        self.assertNotAuthenticated()

    def test_sso_activate_user_new(self):
        # POST registration form
        data = {
            'email': 'sso_new@mit.edu', 'username': 'ssonew', 'first_names': 'SSO', 'last_name': 'New',
            'privacy_policy': 'True'
        }
        response = self.client.post(reverse('sso_register'), data=data, HTTP_REMOTE_USER='new_remote_id')

        # GET activation page
        uidb64, token = self.getActivationUrl()
        response = self.client.get(
            reverse('sso_activate_user', args=(uidb64, token)), HTTP_REMOTE_USER='new_remote_id'
        )
        self.assertRedirects(response, reverse('project_home'))
        new_user = User.objects.get(sso_id='new_remote_id')
        self.assertTrue(new_user.is_active)
        self.assertAuthenticatedAs(new_user)

    def test_sso_activate_user_active(self):
        # POST registration form
        data = {
            'email': 'sso_new@mit.edu', 'username': 'ssonew', 'first_names': 'SSO', 'last_name': 'New',
            'privacy_policy': 'True'
        }
        response = self.client.post(reverse('sso_register'), data=data, HTTP_REMOTE_USER='new_remote_id')

        # GET activation page
        uidb64, token = self.getActivationUrl()
        response = self.client.get(
            reverse('sso_activate_user', args=(uidb64, token)), HTTP_REMOTE_USER='new_remote_id'
        )

        # GET activation page again
        response = self.client.get(
            reverse('sso_activate_user', args=(uidb64, token)), HTTP_REMOTE_USER='new_remote_id'
        )
        self.assertRedirects(response, reverse('sso_login'), fetch_redirect_response=False)
