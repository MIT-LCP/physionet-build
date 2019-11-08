from django.contrib.auth.views import LoginView
from django.core import mail
from django.test import TestCase
from django.urls import reverse
import re
import pdb

from user.models import User, AssociatedEmail


class TestAuth(TestCase):
    """
    Test views that require authentication
    """

    def setUp(self):
        self.client.login(username='rgmark@mit.edu', password='Tester11!')

    def test_edit_password(self):
        response = self.client.post(reverse('edit_password'),
            data={'old_password':'Tester11!',
            'new_password1':'Very5trongt0t@11y',
            'new_password2':'Very5trongt0t@11y'})
        self.assertRedirects(response, reverse('edit_password_complete'))
        # Log in using the new password
        self.client.logout()
        self.assertTrue(self.client.login(username='rgmark@mit.edu',
            password='Very5trongt0t@11y'))

    def test_edit_profile(self):
        response = self.client.post(reverse('edit_profile'),
            data={'first_names':'Roger', 'last_name':'Federer',
                  'edit_profile':''})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.get(email='rgmark@mit.edu').profile.last_name,
            'Federer')

    def test_logout(self):
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_profile_fixtures(self):
        """
        Test that the demo profiles in the fixtures are successfully loaded and
        attached to the user objects.
        """
        u = User.objects.get(email='rgmark@mit.edu')
        self.assertTrue(u.profile.last_name == 'Mark')

    def test_user_settings(self):
        response = self.client.get(reverse('user_settings'))
        self.assertRedirects(response, reverse('edit_profile'))


class TestPublic(TestCase):
    """
    Test views that do not require authentication
    """

    def test_admin_home(self):
        """
        Test that the admin page redirects to a login page.
        """
        response = self.client.get('/admin/')
        self.assertRedirects(response, '/admin/login/?next=/admin/',
            status_code=302)

    def test_login(self):
        response = self.client.post(reverse('login'),
            data={'username':'rgmark@mit.edu','password':'Tester11!'})
        self.assertRedirects(response, reverse('project_home'))
        self.assertIn('_auth_user_id', self.client.session)

    def test_reset_password(self):
        """
        Test the full reset password functionality
        """
        # Request the password reset
        response = self.client.post(reverse('reset_password_request'),
            data={'email':'rgmark@mit.edu'})
        self.assertRedirects(response, reverse('reset_password_sent'))

        # Get the reset info from the email
        uidb64, token = re.findall('reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[0].body)[0]

        # Visit the reset url which redirects to the password set form
        response = self.client.get(reverse('reset_password_confirm',
            kwargs={'uidb64':uidb64,'token':token}))
        self.assertRedirects(response, reverse('reset_password_confirm',
            kwargs={'uidb64':uidb64, 'token':'set-password'}))

        # Set the new password
        response = self.client.post(response.url,
            data={'new_password1':'Very5trongt0t@11y',
                'new_password2':'Very5trongt0t@11y'})
        self.assertRedirects(response, reverse('reset_password_complete'))
        # Log in using the new password
        self.assertTrue(self.client.login(username='rgmark@mit.edu',
            password='Very5trongt0t@11y'))


class TestCredentialing(TestCase):
    """
    Test credentialing logic
    """

    def test_registration_credential(self):
        """
        Tests the automatic migration of the credentialing status from
        their old pn account upon successful registration/activation.

        Ensures that the same legacy credential cannot be carried over
        more than once.

        """
        # Register and activate a user with old credentialed account
        response = self.client.post(reverse('register'),
            data={'email':'admin@upr.edu', 'username':'adminupr',
            'first_names': 'admin', 'last_name': 'upr',
            'password1':'Very5trongt0t@11y', 'password2':'Very5trongt0t@11y'})
        uidb64, token = re.findall('activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[-1].body)[0]
        response = self.client.get(reverse('activate_user',
            kwargs={'uidb64':uidb64,'token':token}))

        # Check if the user is active and credentialed
        self.assertTrue(User.objects.get(email='admin@upr.edu').is_active)
        self.assertTrue(User.objects.get(email='admin@upr.edu').is_credentialed)

        # Add and verify another email.
        self.client.login(username='admin@upr.edu', password='Very5trongt0t@11y')
        response = self.client.post(reverse('edit_emails'), data={'add_email':True, 'email': 'not_credentialed@upr.edu'})
        uidb64, token = re.findall('verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[-1].body)[0]
        response = self.client.get(reverse('verify_email',
            kwargs={'uidb64':uidb64,'token':token}))
        # Set the new email as primary and remove the original
        response = self.client.post(reverse('edit_emails'), data={
            'set_primary_email':True,
            'associated_email': 'not_credentialed@upr.edu'})
        AssociatedEmail.objects.get(email='admin@upr.edu').delete()
        self.client.logout()

        # Another person tries to register again with that same email
        # hoping to get automatic credentialing
        response = self.client.post(reverse('register'),
            data={'email':'admin@upr.edu', 'username':'sneakyfriend',
            'first_names': 'admin', 'last_name': 'upr',
            'password1':'Very5trongt0t@11y', 'password2':'Very5trongt0t@11y'})
        uidb64, token = re.findall('activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[-1].body)[0]
        response = self.client.get(reverse('activate_user',
            kwargs={'uidb64':uidb64,'token':token}))

        # The user is not automatically credentialed because the email's
        # credentialing status was already migrated to the other account
        self.assertTrue(User.objects.get(email='admin@upr.edu').is_active)
        self.assertFalse(User.objects.get(email='admin@upr.edu').is_credentialed)

    def test_new_email_credential(self):
        """
        Tests the automatic migration of the credentialing status from
        their old pn account upon adding an associated email.

        Ensures that the same legacy credential cannot be carried over
        more than once.

        """
        # Add and verify a credentialed email
        self.client.login(username='admin@mit.edu', password='Tester11!')
        response = self.client.post(reverse('edit_emails'), data={'add_email': True, 'email': 'admin@upr.edu'})
        uidb64, token = re.findall('verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[-1].body)[0]
        response = self.client.get(reverse('verify_email',
            kwargs={'uidb64':uidb64,'token':token}))

        # Check that the user is credentialed
        self.assertTrue(User.objects.get(email='admin@mit.edu').is_credentialed)
        # Remove the email
        AssociatedEmail.objects.get(email='admin@upr.edu').delete()
        self.client.logout()

        # Another person tries to add that same email hoping to get
        # automatic credentialing
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        response = self.client.post(reverse('edit_emails'), data={'add_email': True, 'email': 'admin@upr.edu'})
        uidb64, token = re.findall('verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[-1].body)[0]
        response = self.client.get(reverse('verify_email',
            kwargs={'uidb64':uidb64,'token':token}))

        # The user is not automatically credentialed because the email's
        # credentialing status was already migrated to the other account
        self.assertEqual(User.objects.get(email='aewj@mit.edu'), AssociatedEmail.objects.get(email='admin@upr.edu').user)
        self.assertFalse(User.objects.get(email='aewj@mit.edu').is_credentialed)
