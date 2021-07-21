import datetime
import logging
import os
import pdb
import re
import shutil

from django.conf import settings
from lightwave.views import DBCAL_FILE, ORIGINAL_DBCAL_FILE
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from user.models import AssociatedEmail, Profile, User
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
        Symlink dbcal file to the testing effective static root.

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

        if os.path.exists(ORIGINAL_DBCAL_FILE):
            os.symlink(ORIGINAL_DBCAL_FILE, DBCAL_FILE)

        # Published project files should have been made read-only at
        # the time of publication
        for topdir in (settings.MEDIA_ROOT, self.test_static_root):
            ppdir = os.path.join(topdir, 'published-projects')
            for dirpath, subdirs, files in os.walk(ppdir):
                if dirpath != ppdir:
                    for f in files:
                        os.chmod(os.path.join(dirpath, f), 0o444)
                    for d in subdirs:
                        os.chmod(os.path.join(dirpath, d), 0o555)

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

        # Test 0: login
        self.client.login(username='admin@mit.edu', password='Tester11!')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

        # Test 1: set public email
        self.make_post_request('edit_emails',
            data={'set_public_email': [''], 'associated_email': 'admin3@mit.edu'})
        self.tst_post_request(edit_emails)
        # order is admin2@mit.edu, admin3@mit.edu, admin@mit.edu
        public_status = [ae.is_public for ae in AssociatedEmail.objects.filter(user=self.user).order_by('email')]
        self.assertEqual(public_status, [False, True, False])

        # Test 2: set primary email
        self.make_post_request('edit_emails',
            data={'set_primary_email': [''], 'associated_email': 'admin2@mit.edu'})
        self.tst_post_request(edit_emails)
        self.assertEqual(self.user.email, 'admin2@mit.edu')

        # Test 3: add email
        response = self.client.post(reverse('edit_emails'), data={
            'add_email': [''], 'email': 'tester0@mit.edu'})
        self.assertIsNotNone(AssociatedEmail.objects.filter(email='tester0@mit.edu'))

        # Test 4: remove email
        remove_id = AssociatedEmail.objects.get(email='admin3@mit.edu').id
        self.make_post_request('edit_emails',
            data={'remove_email': [str(remove_id)]})
        self.tst_post_request(edit_emails)
        remaining_associated_emails = [ae.email for ae in AssociatedEmail.objects.filter(user=self.user)]
        self.assertNotIn('admin3@mit.edu', remaining_associated_emails)

        # Test 5: Verify the newly added email
        # Get the activation info from the sent email
        uidb64, token = re.findall('http://localhost:8000/verify/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{20})/',
            mail.outbox[0].body)[0]

        request = self.client.get(reverse('verify_email', args=(uidb64, token)))
        self.assertTrue(AssociatedEmail.objects.get(email='tester0@mit.edu').is_verified)

    def test_purgeaccounts(self):
        # Test 0: login
        self.client.login(username='admin@mit.edu', password='Tester11!')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

        # Test 1: add email
        self.client.post(reverse('edit_emails'), data={
            'add_email': [''], 'email': 'tester2@mit.edu'})
        self.assertIsNotNone(AssociatedEmail.objects.filter(email='tester2@mit.edu'))

        # Test 2: add email to be removed
        self.client.post(reverse('edit_emails'), data={
            'add_email': [''], 'email': 'tester1@mit.edu'})
        self.assertIsNotNone(AssociatedEmail.objects.filter(email='tester1@mit.edu'))

        email1 = AssociatedEmail.objects.get(email='tester1@mit.edu')
        email1.added_date -= timezone.timedelta(days=30)
        email1.save()
        email1_id = email1.id

        email2 = AssociatedEmail.objects.get(email='tester2@mit.edu')
        email2_id = email2.id

        call_command('purgeaccounts')

        self.assertFalse(AssociatedEmail.objects.filter(id=email1_id).exists())
        self.assertTrue(AssociatedEmail.objects.filter(id=email2_id).exists())


class TestPublic(TestMixin):
    """
    Test views that do not require authentication
    """

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.user = AnonymousUser()

    def test_public_profile(self):
        self.make_get_request('public_profile', {'username': 'admin'})
        self.tst_get_request(public_profile,
            view_kwargs={'username': 'admin'}, status_code=200)

    def test_register_activate(self):
        """
        Test user account registration and activation
        """
        # Register the new user
        self.make_get_request('register')
        self.tst_get_request(register, status_code=200)
        self.make_post_request('register',
            data={'email': 'jackreacher@mit.edu', 'username': 'awesomeness',
            'first_names': 'Jack', 'last_name': 'Reacher',
            'password1': 'Very5trongt0t@11y', 'password2': 'Very5trongt0t@11y'})
        # Recall that register uses same view upon success, so not 302
        self.tst_post_request(register, status_code=200)
        # Check user object was created
        self.assertIsNotNone(User.objects.filter(email='jackreacher@mit.edu'))
        self.assertFalse(User.objects.get(email='jackreacher@mit.edu').is_active)

        # Get the activation info from the sent email
        uidb64, token = re.findall('http://localhost:8000/activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/',
            mail.outbox[0].body)[0]
        # Visit the activation link
        response = self.client.get(reverse('activate_user', args=(uidb64, token)))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session['_activation_reset_token'], token)

        response = self.client.post(reverse('activate_user',
            args=(uidb64, 'user-activation')),
            data={'email': 'jackreacher@mit.edu', 'username': 'awesomeness',
            'password1': 'Very5trongt0t@11y', 'password2': 'Very5trongt0t@11y'})
        # Test that the user is active
        self.assertTrue(User.objects.get(email='jackreacher@mit.edu').is_active)

        self.client.get(reverse('activate_user', args=(uidb64, token)))

    def test_purgeaccounts(self):
        """
        Test automatic deletion of unactivated accounts.
        """

        num_active_accounts = User.objects.filter(is_active=True).count()

        # Register two new user accounts without activating

        self.make_post_request('register', data={
            'email': 'jackreacher@mit.edu', 'username': 'awesomeness',
            'first_names': 'Jack', 'last_name': 'Reacher'})
        self.tst_post_request(register, status_code=200)

        self.make_post_request('register', data={
            'email': 'admin@upr.edu', 'username': 'adminupr',
            'first_names': 'admin', 'last_name': 'upr'})
        self.tst_post_request(register, status_code=200)

        user1 = User.objects.get(email='jackreacher@mit.edu')
        user2 = User.objects.get(email='admin@upr.edu')
        self.assertFalse(user1.is_active)
        self.assertFalse(user2.is_active)

        user1_id = user1.id
        profile1_id = user1.profile.id
        email1_id = user1.associated_emails.get().id

        user2_id = user2.id
        profile2_id = user2.profile.id
        email2_id = user2.associated_emails.get().id

        # Assume the first account was registered 30 days ago
        user1.join_date += datetime.timedelta(days=-30)
        user1.save()

        # Invoke the purgeaccounts command to remove old unactivated
        # accounts
        call_command('purgeaccounts')

        # purgeaccounts should have deleted user1 and the associated
        # Profile and AssociatedEmail objects
        self.assertFalse(User.objects.filter(id=user1_id).exists())
        self.assertFalse(Profile.objects.filter(id=profile1_id).exists())
        self.assertFalse(AssociatedEmail.objects.filter(id=email1_id).exists())

        # purgeaccounts should not have deleted user2
        self.assertTrue(User.objects.filter(id=user2_id).exists())
        self.assertTrue(Profile.objects.filter(id=profile2_id).exists())
        self.assertTrue(AssociatedEmail.objects.filter(id=email2_id).exists())

        # active accounts should be unaffected
        self.assertEqual(num_active_accounts,
                         User.objects.filter(is_active=True).count())
