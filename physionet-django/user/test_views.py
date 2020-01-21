import logging
import os
import pdb
import re
import shutil

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory, TestCase
from django.urls import reverse

from user.models import AssociatedEmail, User
from user.views import (activate_user, edit_emails, edit_profile,
    edit_password_complete, public_profile, register, user_settings,
    verify_email)


def prevent_request_warnings(original_function):
    """
    Decorator to prevent request class from throwing warnings for 404s.

    """
    def new_function(*args, **kwargs):
        # raise logging level to ERROR
        logger = logging.getLogger('django.request')
        previous_logging_level = logger.getEffectiveLevel()
        logger.setLevel(logging.ERROR)
        # trigger original function that would throw warning
        original_function(*args, **kwargs)
        # lower logging level back to previous
        logger.setLevel(previous_logging_level)

    return new_function


class TestMixin(TestCase):
    """
    Mixin for test methods

    Because the fixtures are installed and database is rolled back
    before each setup and teardown respectively, the demo test files
    will be created and destroyed after each test also. We want the
    demo files as well as the demo data reset each time, and individual
    test methods such as publishing projects may change the files.

    Note about inheriting: https://nedbatchelder.com/blog/201210/multiple_inheritance_is_hard.html

    """
    def setUp(self):
        """
        Copy demo media files to the testing media root.
        Copy demo static files to the testing effective static root.

        Does not run collectstatic. The StaticLiveServerTestCase should
        do that automatically for tests that need it.
        """
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        shutil.copytree(os.path.abspath(os.path.join(settings.DEMO_FILE_ROOT, 'media')),
            settings.MEDIA_ROOT)

        self.test_static_root = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATICFILES_DIRS[0]
        shutil.rmtree(self.test_static_root, ignore_errors=True)
        shutil.copytree(os.path.abspath(os.path.join(settings.DEMO_FILE_ROOT, 'static')),
            self.test_static_root)

    def tearDown(self):
        """
        Remove the testing media root
        """
        for root, dirs, files in os.walk(settings.MEDIA_ROOT):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
            for f in files:
                os.chmod(os.path.join(root, f), 0o755)
        for root, dirs, files in os.walk(self.test_static_root):
            for d in dirs:
                os.chmod(os.path.join(root, d), 0o755)
            for f in files:
                os.chmod(os.path.join(root, f), 0o755)

        shutil.rmtree(settings.MEDIA_ROOT)
        shutil.rmtree(self.test_static_root)

    def assertMessage(self, response, level):
        """
        Assert that the max message level in the request equals `level`.

        Can use message success or error to test outcome, since there
        are different cases where forms are reloaded, not present, etc.

        The response code for invalid form submissions are still 200
        so cannot use that to test form submissions.

        """
        self.assertEqual(max(m.level for m in response.context['messages']),
            level)

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


class TestAuth(TestMixin):
    """
    Test views that require authentication
    """

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.user = User.objects.get(email='admin@mit.edu')
        self.anonymous_user = AnonymousUser()

    def test_user_settings(self):
        self.make_get_request('user_settings')
        self.tst_get_request(user_settings, status_code=302,
            redirect_viewname='edit_profile')

    def test_edit_profile(self):
        self.make_get_request('edit_profile')
        self.tst_get_request(edit_profile)

        self.make_post_request('edit_profile',
            data={'first_names': 'Roger', 'last_name': 'Federer'})
        self.tst_post_request(edit_profile)

    def test_edit_password_complete(self):
        self.make_get_request('edit_password_complete')
        self.tst_get_request(edit_password_complete)

    def test_edit_emails(self):
        """
        Test all functions of the edit_emails view:
        - setting email public status
        - set primary email
        - add email
        - remove email

        In addition, also test verification of added email
        """
        self.make_get_request('edit_emails')
        self.tst_get_request(edit_emails)

        # Test 1: set public email
        self.make_post_request('edit_emails',
            data={'set_public_email':[''],'associated_email': 'admin3@mit.edu'})
        self.tst_post_request(edit_emails)
        # order is admin2@mit.edu, admin3@mit.edu, admin@mit.edu
        public_status = [ae.is_public for ae in AssociatedEmail.objects.filter(user=self.user).order_by('email')]
        self.assertEqual(public_status, [False, True, False])

        # Test 2: set primary email
        self.make_post_request('edit_emails',
            data={'set_primary_email':[''],'associated_email': 'admin2@mit.edu'})
        self.tst_post_request(edit_emails)
        self.assertEqual(self.user.email, 'admin2@mit.edu')

        # Test 3: add email
        self.make_post_request('edit_emails',
            data={'add_email':[''],'email': 'tester0@mit.edu'})
        self.tst_post_request(edit_emails)
        self.assertIsNotNone(AssociatedEmail.objects.filter(email='tester0@mit.edu'))

        # Test 4: remove email
        remove_id = AssociatedEmail.objects.get(email='admin3@mit.edu').id
        self.make_post_request('edit_emails',
            data={'remove_email':[str(remove_id)]})
        self.tst_post_request(edit_emails)
        remaining_associated_emails = [ae.email for ae in AssociatedEmail.objects.filter(user=self.user)]
        self.assertNotIn('admin3@mit.edu', remaining_associated_emails)

        # Test 5: Verify the newly added email
        # Get the activation info from the sent email
        uidb64, token = re.findall('http://localhost:8000/verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[0].body)[0]
        self.make_get_request('verify_email', {'uidb64':uidb64, 'token':token})
        self.tst_get_request(verify_email,
            view_kwargs={'uidb64':uidb64, 'token':token})
        self.assertTrue(bool(AssociatedEmail.objects.get(email='tester0@mit.edu').verification_date))


class TestPublic(TestMixin):
    """
    Test views that do not require authentication
    """

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.user = AnonymousUser()

    def test_public_profile(self):
        self.make_get_request('public_profile', {'username':'admin'})
        self.tst_get_request(public_profile,
            view_kwargs={'username':'admin'}, status_code=200)

    def test_register_activate(self):
        """
        Test user account registration and activation
        """
        # Register the new user
        self.make_get_request('register')
        self.tst_get_request(register, status_code=200)
        self.make_post_request('register',
            data={'email':'jackreacher@mit.edu', 'username':'awesomeness',
            'first_names': 'Jack', 'last_name': 'Reacher',
            'password1':'Very5trongt0t@11y', 'password2':'Very5trongt0t@11y'})
        # Recall that register uses same view upon success, so not 302
        self.tst_post_request(register, status_code=200)
        # Check user object was created
        self.assertIsNotNone(User.objects.filter(email='jackreacher@mit.edu'))
        self.assertFalse(User.objects.get(email='jackreacher@mit.edu').is_active)

        # Get the activation info from the sent email
        uidb64, token = re.findall('http://localhost:8000/activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[0].body)[0]
        # Visit the activation link
        self.make_get_request('activate_user', {'uidb64':uidb64, 'token':token})
        self.tst_get_request(activate_user,
            view_kwargs={'uidb64':uidb64, 'token':token})
        # Test that the user is active
        self.assertTrue(User.objects.get(email='jackreacher@mit.edu').is_active)
