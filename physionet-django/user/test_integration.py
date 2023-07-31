import base64

from django.contrib.auth.views import LoginView
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
import re
import pdb

from user.models import User, AssociatedEmail
from user.test_views import TestMixin, offset_system_clock


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


class TestPhoto(TestMixin):
    """
    Test adding/removing profile photo.
    """
    def test_edit_photo(self):
        text_data = b'blah blah'

        pbm_data = b'P4\n1 1\n\x00'

        png_data = base64.b64decode('''
            iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQAAAAA3bvkkAAAACklEQVQIHWNoAAAA
            ggCB8KrjIgAAAABJRU5ErkJggg==
        ''')

        jpeg_data = base64.b64decode('''
            /9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////
            ////////////////////////////////////////////////////////wAALCAAB
            AAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAA//EABQQAQAAAAAAAAAAAAAAAAAA
            AAD/2gAIAQEAAD8AR//Z
        ''')

        self.client.login(username='rgmark@mit.edu', password='Tester11!')

        # upload a PNG image (allowed)
        response = self.client.post(reverse('edit_profile'), data={
            'edit_profile': '', 'first_names': 'Roger', 'last_name': 'Mark',
            'photo': SimpleUploadedFile('photo.jpg', png_data),
        })
        self.assertEqual(response.status_code, 200)
        profile = User.objects.get(email='rgmark@mit.edu').profile
        self.assertTrue(profile.photo)
        self.assertTrue(profile.photo.path.endswith('.png'))

        # delete the image
        response = self.client.post(reverse('edit_profile'), data={
            'delete_photo': '',
        })
        self.assertEqual(response.status_code, 200)
        profile = User.objects.get(email='rgmark@mit.edu').profile
        self.assertFalse(profile.photo)

        # upload some junk
        response = self.client.post(reverse('edit_profile'), data={
            'edit_profile': '', 'first_names': 'Roger', 'last_name': 'Mark',
            'photo': SimpleUploadedFile('photo.png', b'\xff\xd8'),
        })
        self.assertEqual(response.status_code, 200)
        profile = User.objects.get(email='rgmark@mit.edu').profile
        self.assertFalse(profile.photo)

        # upload a PBM image (not allowed)
        response = self.client.post(reverse('edit_profile'), data={
            'edit_profile': '', 'first_names': 'Roger', 'last_name': 'Mark',
            'photo': SimpleUploadedFile('photo.jpg', pbm_data),
        })
        self.assertEqual(response.status_code, 200)
        profile = User.objects.get(email='rgmark@mit.edu').profile
        self.assertFalse(profile.photo)

        # upload a JPEG image (allowed)
        response = self.client.post(reverse('edit_profile'), data={
            'edit_profile': '', 'first_names': 'Roger', 'last_name': 'Mark',
            'photo': SimpleUploadedFile('asdfghjk', jpeg_data),
        })
        self.assertEqual(response.status_code, 200)
        profile = User.objects.get(email='rgmark@mit.edu').profile
        self.assertTrue(profile.photo)
        self.assertTrue(profile.photo.path.endswith('.jpg'))


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
        uidb64, token = re.findall(
            r'reset/(?P<uidb64>[0-9A-Za-z_\-]+)/'
            r'(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/',
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


class TestCredentialing(TestMixin):
    """
    Test credentialing logic
    """

    def test_credential_application(self):
        """
        Test submission of a credential application.
        """

        # User who has no application pending
        u = User.objects.get(username='eulaeasley')
        self.assertFalse(u.credential_applications.exists())

        self.client.login(username='eulaeasley', password='Tester11!')

        data = {
            'application-first_names': 'Eula',
            'application-last_name': 'Easley',
            'application-suffix': '',
            'application-researcher_category': '2',
            'application-organization_name': 'MIT',
            'application-job_title': 'Debugger',
            'application-city': 'Cambridge',
            'application-state_province': 'MA',
            'application-zip_code': '02139',
            'application-country': 'US',
            'application-webpage': '',
            'application-reference_category': '1',
            'application-reference_name': 'Charlie Root',
            'application-reference_email': 'root@example.com',
            'application-reference_organization': 'MIT',
            'application-reference_title': 'Administrator',
            'application-research_summary': 'I plan to access the MIMIC IV dataset and the \
            Pediatric Intensive Care database.The datasets will be used to predict the \
            outcome of pediatric anesthesia using machine learning.',
        }

        self.client.post(reverse('credential_application'), data=data)
        # no message upon successful submission
        self.assertTrue(u.credential_applications.exists())

    def test_registration_credential(self):
        """
        Tests the automatic migration of the credentialing status from
        their old pn account upon successful registration/activation.

        Ensures that the same legacy credential cannot be carried over
        more than once.

        """
        # Load registration page 60 seconds ago
        with offset_system_clock(seconds=-60):
            self.client.get(reverse('register'))

        # Register and activate a user with old credentialed account
        response = self.client.post(reverse('register'),
                                    data={'email': 'admin@upr.edu', 'username': 'adminupr',
                                          'first_names': 'admin', 'last_name': 'upr', 'privacy_policy': 'True'})
        uidb64, token = re.findall(
            r'activate/(?P<uidb64>[0-9A-Za-z_\-]+)/'
            r'(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/',
            mail.outbox[-1].body)[0]

        response = self.client.get(reverse('activate_user', args=(uidb64, token)))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session['_activation_reset_token'], token)

        response = self.client.post(reverse('activate_user',
            args=(uidb64, 'user-activation')),
            data={'email':'admin@upr.edu', 'username': 'adminupr',
            'password1': 'Very5trongt0t@11y', 'password2': 'Very5trongt0t@11y'})

        # Check if the user is active and credentialed
        self.assertTrue(User.objects.get(email='admin@upr.edu').is_active)
        self.assertTrue(User.objects.get(email='admin@upr.edu').is_credentialed)

        # Add and verify another email.
        self.client.login(username='admin@upr.edu', password='Very5trongt0t@11y')
        response = self.client.post(reverse('edit_emails'), data={'add_email':True, 'email': 'not_credentialed@upr.edu'})
        uidb64, token = re.findall('verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{20})/',
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
        with offset_system_clock(seconds=-60):
            self.client.get(reverse('register'))
        response = self.client.post(reverse('register'),
            data={'email':'admin@upr.edu', 'username':'sneakyfriend',
                  'first_names': 'admin', 'last_name': 'upr',
                  'password1': 'Very5trongt0t@11y', 'password2': 'Very5trongt0t@11y', 'privacy_policy': 'True'})

        uidb64, token = re.findall(
            r'activate/(?P<uidb64>[0-9A-Za-z_\-]+)/'
            r'(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/',
            mail.outbox[-1].body)[0]

        response = self.client.get(reverse('activate_user', args=(uidb64, token)))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session['_activation_reset_token'], token)

        response = self.client.post(reverse('activate_user',
            args=(uidb64, 'user-activation')),
            data={'email': 'admin@upr.edu', 'username': 'adminupr',
            'password1': 'Very5trongt0t@11y', 'password2': 'Very5trongt0t@11y'})

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
        uidb64, token = re.findall('verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{20})/',
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
        self.client.login(username='george@mit.edu', password='Tester11!')
        response = self.client.post(reverse('edit_emails'), data={'add_email': True, 'email': 'admin@upr.edu'})
        uidb64, token = re.findall('verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{20})/',
            mail.outbox[-1].body)[0]
        response = self.client.get(reverse('verify_email',
            kwargs={'uidb64':uidb64,'token':token}))

        # The user is not automatically credentialed because the email's
        # credentialing status was already migrated to the other account
        self.assertEqual(User.objects.get(email='george@mit.edu'), AssociatedEmail.objects.get(email='admin@upr.edu').user)
        self.assertFalse(User.objects.get(email='george@mit.edu').is_credentialed)
