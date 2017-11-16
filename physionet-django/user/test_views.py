from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory, TestCase
from django.urls import reverse
import re

from user.models import AssociatedEmail, User
from user.management.commands.resetdb import load_fixture_profiles
from user.views import (activate_user, edit_emails, edit_profile,
    edit_password_done, public_profile, register, user_home, user_settings,
    verify_email)

import pdb

# Add decorator to test invalid users



class TestMixin(object):
    """
    Mixin for test methods
    """
    def make_get_request(self, viewname, reverse_kwargs=None):
        """
        Helper Function.
        Create and set a get request
    
        - viewname: The view name
        - reverse_kwargs: kwargs of additional url parameters
        """
        self.get_request = self.factory.get(reverse(viewname,
            kwargs=reverse_kwargs))
        self.get_request.user = self.user

    def make_post_request(self, viewname, data, reverse_kwargs=None):
        """
        Helper Function.
        Create and set a get request
    
        - viewname: The view name
        - data: Dictionary of post parameters
        - reverse_kwargs: Kwargs of additional url parameters
        """
        self.post_request = self.factory.post(reverse(viewname,
            kwargs=reverse_kwargs), data)
        self.post_request.user = self.user
        # Provide the message object to the request because middleware
        # is not supported by RequestFactory
        setattr(self.post_request, 'session', 'session')
        messages = FallbackStorage(self.post_request)
        setattr(self.post_request, '_messages', messages)

    def tst_get_request(self, view, view_kwargs=None, status_code=200,
        redirect_viewname=None, redirect_reverse_kwargs=None):
        """
        Helper Function.
        Test the get request with the view against the expected status code
        
        - view: The view function
        - view_kwargs: The kwargs dictionary of additional arguments to put into
          view function aside from request
        - status_code: expected status code of response
        - redirect_viewname: view name of the expected redirect
        - redirect_reverse_kwargs: kwargs dictionary of expected redirect 
        """
        if view_kwargs:
            response = view(self.get_request, **view_kwargs)
        else:
            response = view(self.get_request)
        self.assertEqual(response.status_code, status_code)
        if status_code == 302:
            # We don't use assertRedirects because the response has no client
            self.assertEqual(response['location'], reverse(redirect_viewname,
                kwargs=redirect_reverse_kwargs))

    def tst_post_request(self, view, view_kwargs=None, status_code=200,
        redirect_viewname=None, redirect_reverse_kwargs=None):
        """
        Helper Function.
        Test the post request with the view against the expected status code
        
        - view: The view function
        - view_kwargs: The kwargs dictionary of additional arguments to put into
          view function aside from request
        - status_code: expected status code of response
        - redirect_viewname: view name of the expected redirect
        - redirect_reverse_kwargs: kwargs dictionary of expected redirect 
        """
        if view_kwargs:
            response = view(self.post_request, **view_kwargs)
        else:
            response = view(self.post_request)
        self.assertEqual(response.status_code, status_code)
        if status_code == 302:
            self.assertEqual(response['location'], reverse(redirect_viewname,
                kwargs=redirect_reverse_kwargs))


class TestAuthViews(TestCase, TestMixin):
    """
    Test views that require authentication
    """
    fixtures = ['user']

    def setUp(self):
        load_fixture_profiles()
        self.factory = RequestFactory()
        self.user = User.objects.get(email='tester@mit.edu')
        self.anonymous_user = AnonymousUser()

    def test_user_home(self):
        self.make_get_request('user_home')
        self.tst_get_request(user_home)

    def test_user_settings(self):
        self.make_get_request('user_settings')
        self.tst_get_request(user_settings, status_code=302,
            redirect_viewname='edit_profile')

    def test_edit_profile(self):
        self.make_get_request('edit_profile')
        self.tst_get_request(edit_profile)

        self.make_post_request('edit_profile',
            data={'first_name': 'Roger', 'last_name': 'Federer'})
        self.tst_post_request(edit_profile)

    def test_edit_password_done(self):
        self.make_get_request('edit_password_done')
        self.tst_get_request(edit_password_done)

    def test_edit_emails(self):
        self.make_get_request('edit_emails')
        self.tst_get_request(edit_emails)
        # Test 1: change public email status
        self.make_post_request('edit_emails',
            data={'associated_emails-TOTAL_FORMS': ['3'],
            'associated_emails-0-id': ['1'],
            'associated_emails-INITIAL_FORMS': ['3'],
            'associated_emails-0-user': ['1'],
            'associated_emails-1-email': ['tester2@mit.edu'],
            'set_public_emails': [''], 'associated_emails-2-is_public': ['on'],
            'associated_emails-MIN_NUM_FORMS': ['0'],
            'associated_emails-1-is_public': ['on'],
            'associated_emails-1-user': ['1'],
            'associated_emails-1-id': ['4'],
            'associated_emails-2-id': ['5'],
            'associated_emails-2-email': ['tester3@mit.edu'],
            'associated_emails-MAX_NUM_FORMS': ['3'],
            'associated_emails-2-is_primary_email': ['False'],
            'associated_emails-0-is_public': ['on'],
            'associated_emails-0-email': ['tester@mit.edu'],
            'associated_emails-2-user': ['1'],
            'associated_emails-1-is_primary_email': ['False'],
            'associated_emails-0-is_primary_email': ['True']})
        self.tst_post_request(edit_emails)
        public_status = [ae.is_public for ae in AssociatedEmail.objects.filter(user=self.user)]
        self.assertFalse(False in public_status)
        # Test 2: change primary email
        self.make_post_request('edit_emails',
            data={'set_primary_email':[''],'associated_email': 'tester2@mit.edu'})
        self.tst_post_request(edit_emails)
        self.assertEqual(self.user.email, 'tester2@mit.edu')
        # Test 3: add email, and subsequent verify email
        self.make_post_request('edit_emails',
            data={'add_email':[''],'associated_email': 'tester0@mit.edu'})
        self.tst_post_request(edit_emails)
        self.assertIsNotNone(AssociatedEmail.objects.filter(email='tester0@mit.edu'))



        # Test 4: remove email
        self.make_post_request('edit_emails',
            data={'remove_email':[''],'associated_email': 'tester3@mit.edu'})
        self.tst_post_request(edit_emails)
        remaining_associated_emails = [ae.email for ae in AssociatedEmail.objects.filter(user=self.user)]
        self.assertFalse('tester3@mit.edu' in remaining_associated_emails)


class TestPublicViews(TestCase, TestMixin):
    """
    Test views that do not require authentication
    """
    fixtures = ['user']

    def setUp(self):
        load_fixture_profiles()
        self.factory = RequestFactory()
        self.user = AnonymousUser()

    def test_public_profile(self):
        self.make_get_request('public_profile', {'email':'tester@mit.edu'})
        self.tst_get_request(public_profile,
            view_kwargs={'email':'tester@mit.edu'}, status_code=200)

    def test_register_activate(self):
        """
        Test user account registration and activation
        """
        # Registration
        self.make_get_request('register')
        self.tst_get_request(register, status_code=200)
        self.make_post_request('register',
            data={'email':'jackreacher@mit.edu', 'first_name': 'Jack',
            'last_name': 'Reacher','password1':'Very5trongt0t@11y',
            'password2':'Very5trongt0t@11y'})
        # Recall that register uses same view upon success, so not 302
        self.tst_post_request(register, status_code=200)
        # Check user object was created
        self.assertIsNotNone(User.objects.filter(email='jackreacher@mit.edu'))
        self.assertFalse(User.objects.get(email='jackreacher@mit.edu').is_active)
        # Get the activation info from the sent email
        uidb64, token = re.findall('http://testserver/activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[0].body)[0]
        # Activation
        self.make_get_request('activate_user', {'uidb64':uidb64, 'token':token})
        self.tst_get_request(activate_user,
            view_kwargs={'uidb64':uidb64, 'token':token})
        self.assertTrue(User.objects.get(email='jackreacher@mit.edu').is_active)

