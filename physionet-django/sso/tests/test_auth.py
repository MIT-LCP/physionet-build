from django.test import TestCase
from sso.auth import RemoteUserBackend
from user.models import User


class TestAuth(TestCase):
    def setUp(self):
        self.inactive_user = User.objects.create(
            username='sso_inactive', email='sso_inactive@mit.edu', sso_id='inactive_remote_id'
        )
        self.active_user = User.objects.create(
            username='sso_active', email='sso_active@mit.edu', sso_id='active_remote_id', is_active=True
        )
        self.request = None  # Request is not used

    def test_authenticate_active(self):
        user = RemoteUserBackend().authenticate(self.request, remote_user=self.active_user.sso_id)
        self.assertEqual(self.active_user, user)

    def test_authenticate_inactive(self):
        user = RemoteUserBackend().authenticate(self.request, remote_user=self.inactive_user.sso_id)
        self.assertIsNone(user)

    def test_authenticate_missing(self):
        user = RemoteUserBackend().authenticate(self.request, remote_user='missing_remote_user')
        self.assertIsNone(user)

    def test_authenticate_none(self):
        user = RemoteUserBackend().authenticate(self.request, remote_user=None)
        self.assertIsNone(user)

    def test_get_user_active(self):
        user = RemoteUserBackend().get_user(user_id=self.active_user.id)
        self.assertEqual(self.active_user, user)

    def test_get_user_inactive(self):
        user = RemoteUserBackend().get_user(user_id=self.inactive_user.id)
        self.assertIsNone(user)

    def test_get_user_missing(self):
        user = RemoteUserBackend().get_user(user_id=123456789)
        self.assertIsNone(user)

    def test_get_user_none(self):
        user = RemoteUserBackend().get_user(user_id=None)
        self.assertIsNone(user)
