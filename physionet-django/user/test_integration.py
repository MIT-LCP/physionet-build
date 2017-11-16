from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.views import LoginView
from django.test import TestCase
from django.urls import reverse

from user.models import User, AssociatedEmail
from user.management.commands.resetdb import load_fixture_profiles
from user.views import (activate_user, set_primary_email, set_public_emails,
    add_email, remove_email, edit_emails, edit_profile, edit_password_done, public_profile, register, user_home, user_settings, verify_email)

import pdb


class TestAuth(TestCase):
    """
    Test views that require authentication
    """
    fixtures = ['user']

    def setUp(self):
        load_fixture_profiles()
        self.client.login(username='rgmark@mit.edu', password='Tester1!')

    def test_profile_fixtures(self):
        """
        Test that the demo profiles in the fixtures are successfully loaded and
        attached to the user objects.
        """
        u = User.objects.get(email='rgmark@mit.edu')
        self.assertTrue(u.profile.last_name == 'Mark')

    def test_edit_password(self):
        response = self.client.post(reverse('edit_password'),
            data={'old_password':'Tester1!',
            'new_password1':'Very5trongt0t@11y',
            'new_password2':'Very5trongt0t@11y'})
        self.assertRedirects(response, reverse('edit_password_done'))
        # Try to log in using the new password
        self.client.logout()
        self.assertTrue(self.client.login(username='rgmark@mit.edu',
            password='Very5trongt0t@11y'))

    def test_user_settings(self):
        response = self.client.get(reverse('user_settings'))
        self.assertRedirects(response, reverse('edit_profile'))

    def test_logout(self):
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('home'))

    def test_edit_profile(self):
        response = self.client.post(reverse('edit_profile'),
            data={'first_name':'Roger', 'last_name':'Federer'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.get(email='rgmark@mit.edu').profile.last_name,
            'Federer')


class TestPublic(TestCase):
    """
    Test views that do not require authentication
    """

    fixtures = ['user']

    def setUp(self):
        load_fixture_profiles()

    def test_admin_home(self):
        """
        Test that the admin page redirects to a login page.
        """
        response = self.client.get('/admin/')
        self.assertRedirects(response,'/admin/login/?next=/admin/',
            status_code=302)

    def test_login(self):
        response = self.client.post(reverse('login'),
            data={'username':'rgmark@mit.edu','password':'Tester1!'})
        self.assertRedirects(response, reverse('user_home'))


