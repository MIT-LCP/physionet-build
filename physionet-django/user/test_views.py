import contextlib
import datetime
import logging
import os
import pdb
import re
import shutil
import time

from django.conf import settings

from lightwave.views import DBCAL_FILE, ORIGINAL_DBCAL_FILE
from django.contrib import messages as msgs
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from user.enums import TrainingStatus
from user.models import AssociatedEmail, Profile, User, Training, TrainingType, Question, TrainingQuestion
from user.views import (activate_user, edit_emails, edit_profile,
    edit_password_complete, public_profile, register, user_settings,
    verify_email)

from unittest.mock import patch


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


@contextlib.contextmanager
def offset_system_clock(**kwargs):
    """
    Context manager to shift the apparent system clock time.

    The keyword arguments are used to construct a time offset (see the
    standard datetime.timedelta class).  During execution of the
    context manager, the standard functions 'time.time',
    'datetime.datetime.now', and 'datetime.datetime.utcnow' will
    return an offset time value.
    """
    delta = datetime.timedelta(**kwargs)

    # This is a bit of a kludge; it seems like it should be possible
    # to do this more elegantly using unittest.mock (perhaps using
    # unittest.mock.patch.)  However, the obvious approaches fail in
    # strange ways (mostly because datetime.datetime is built-in and
    # immutable.)

    real_time = time.time

    def fake_time():
        return real_time() + delta.total_seconds()

    real_datetime = datetime.datetime

    class fake_datetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(fake_time(), tz)

        @classmethod
        def utcnow(cls):
            return cls.utcfromtimestamp(fake_time())

    try:
        time.time = fake_time
        datetime.datetime = fake_datetime
        yield
    finally:
        time.time = real_time
        datetime.datetime = real_datetime


def _force_delete_tree(path):
    """
    Recursively delete a directory tree, including read-only directories.
    """
    if os.path.exists(path):
        # Make each (recursive) subdirectory writable, so that we can
        # delete files from it.
        for subdir, _, _ in os.walk(path):
            os.chmod(subdir, 0o700)
        shutil.rmtree(path)


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
        _force_delete_tree(settings.MEDIA_ROOT)
        shutil.copytree(os.path.abspath(os.path.join(settings.DEMO_FILE_ROOT, 'media')),
            settings.MEDIA_ROOT)

        self.test_static_root = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATICFILES_DIRS[0]
        _force_delete_tree(self.test_static_root)
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
        _force_delete_tree(settings.MEDIA_ROOT)
        _force_delete_tree(self.test_static_root)

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

    def test_email_limit(self):
        """
        Test that the user cannot add more than allowed settings.MAX_EMAILS_PER_USER emails
        """
        # Test 0: login
        self.client.login(username='admin@mit.edu', password='Tester11!')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

        total_associated_emails = AssociatedEmail.objects.filter(user=self.user).count()

        # Test 1: add emails until limit is reached
        for i in range(total_associated_emails, settings.MAX_EMAILS_PER_USER):
            email_to_add = f'tester{i}@mit.edu'
            self.client.post(reverse('edit_emails'), data={'add_email': [''], 'email': email_to_add})
            self.assertIsNotNone(AssociatedEmail.objects.filter(email=email_to_add))

        # Test 2: add one more email
        email_to_add = f'tester{settings.MAX_EMAILS_PER_USER}@mit.edu'
        self.client.post(reverse('edit_emails'), data={'add_email': [''], 'email': email_to_add})
        self.assertFalse(AssociatedEmail.objects.filter(email=email_to_add))

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
        # Clear cookies
        self.client.logout()
        # Load registration page
        self.client.get(reverse('register'))
        # Try to register
        response = self.client.post(reverse('register'), data={
            'email': 'jackreacher@mit.edu', 'username': 'awesomeness',
            'first_names': 'Jack', 'last_name': 'Reacher', 'privacy_policy': 'True'})
        # User object should not have been created, since we submitted
        # the form too quickly
        self.assertFalse(User.objects.filter(username='awesomeness'))

        # Load registration page 60 seconds ago
        with offset_system_clock(seconds=-60):
            self.client.get(reverse('register'))

        # Register the new user
        response = self.client.post(reverse('register'), data={
            'email': 'jackreacher@mit.edu', 'username': 'awesomeness',
            'first_names': 'Jack', 'last_name': 'Reacher', 'privacy_policy': 'True'})
        # Recall that register uses same view upon success, so not 302
        self.assertEqual(response.status_code, 200)
        # Check user object was created
        self.assertTrue(User.objects.filter(email='jackreacher@mit.edu'))
        self.assertFalse(User.objects.get(email='jackreacher@mit.edu').is_active)

        # Get the activation info from the sent email
        uidb64, token = re.findall(
            r'http://localhost:8000/activate/'
            r'(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/',
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

        with offset_system_clock(seconds=-60):
            self.client.get(reverse('register'))
        response = self.client.post(reverse('register'), data={
            'email': 'jackreacher@mit.edu', 'username': 'awesomeness',
            'first_names': 'Jack', 'last_name': 'Reacher', 'privacy_policy': 'True'})
        self.assertEqual(response.status_code, 200)

        with offset_system_clock(seconds=-60):
            self.client.get(reverse('register'))
        response = self.client.post(reverse('register'), data={
            'email': 'admin@upr.edu', 'username': 'adminupr',
            'first_names': 'admin', 'last_name': 'upr', 'privacy_policy': 'True'})
        self.assertEqual(response.status_code, 200)

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


class TrainingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.training_url = reverse('edit_training')
        cls.login_url = reverse('login')
        cls.console_training_url = reverse('training_list', kwargs={'status': 'review'})
        cls.user = User.objects.create(username='user', email='user@example.com')
        cls.admin = User.objects.create_admin(username='admin_user', email='admin@example.com', password='Tester11!')
        cls.profile = Profile.objects.create(user=cls.user, first_names="Rafał", last_name="F")

        cls.question = Question.objects.create(content='Is it okay?')
        cls.training_type_1 = TrainingType.objects.create(name='Example', valid_duration=datetime.timedelta(days=10))
        cls.training_type_2 = TrainingType.objects.create(name='Another', valid_duration=datetime.timedelta(days=10))
        cls.training_type_1.questions.add(cls.question)
        cls.training_type_2.questions.add(cls.question)

        training_completion_report = SimpleUploadedFile(
            "hello_world.pdf",
            b"Hello World"
        )
        cls.training = Training.objects.create(
            training_type=cls.training_type_2,
            user=cls.user,
            completion_report=training_completion_report)
        training_question = TrainingQuestion.objects.create(training=cls.training, question=cls.question)
        cls.training_view_url = reverse('edit_training_detail', kwargs={'training_id': cls.training.pk})

        cls.training_process_url = reverse('training_process', kwargs={'pk': cls.training.pk})
        cls.training_process_data = {
            'form-TOTAL_FORMS': ['1'],
            'form-INITIAL_FORMS': ['1'],
            'form-MIN_NUM_FORMS': ['0'],
            'form-MAX_NUM_FORMS': ['1000'],
            'form-0-id': [str(training_question.pk)],
        }

    def setUp(self):
        pdf_content = b'%PDF-1.3\n%\x93\x8c\x8b\x9e ReportLab Generated PDF document http://www.reportlab.com\n1 0 obj\n<<\n/F1 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/BaseFont /Helvetica /Encoding /WinAnsiEncoding /Name /F1 /Subtype /Type1 /Type /Font\n>>\nendobj\n3 0 obj\n<<\n/Contents 7 0 R /MediaBox [ 0 0 595.2756 841.8898 ] /Parent 6 0 R /Resources <<\n/Font 1 0 R /ProcSet [ /PDF /Text /ImageB /ImageC /ImageI ]\n>> /Rotate 0 /Trans <<\n\n>> \n  /Type /Page\n>>\nendobj\n4 0 obj\n<<\n/PageMode /UseNone /Pages 6 0 R /Type /Catalog\n>>\nendobj\n5 0 obj\n<<\n/Author (anonymous) /CreationDate (D:20221219130742+05\'00\') /Creator (ReportLab PDF Library - www.reportlab.com) /Keywords () /ModDate (D:20221219130742+05\'00\') /Producer (ReportLab PDF Library - www.reportlab.com) \n  /Subject (unspecified) /Title (untitled) /Trapped /False\n>>\nendobj\n6 0 obj\n<<\n/Count 1 /Kids [ 3 0 R ] /Type /Pages\n>>\nendobj\n7 0 obj\n<<\n/Filter [ /ASCII85Decode /FlateDecode ] /Length 104\n>>\nstream\nGapQh0E=F,0U\\H3T\\pNYT^QKk?tc>IP,;W#U1^23ihPEM_M(M8&8HllJH6UCj=4hfUupb!lR8"\\(ZhG@C+=mI.>2AcPUg\\R!\'_YE[f~>endstream\nendobj\nxref\n0 8\n0000000000 65535 f \n0000000073 00000 n \n0000000104 00000 n \n0000000211 00000 n \n0000000414 00000 n \n0000000482 00000 n \n0000000778 00000 n \n0000000837 00000 n \ntrailer\n<<\n/ID \n[<cb45d718ea09b37c9695ca3758dbd4ba><cb45d718ea09b37c9695ca3758dbd4ba>]\n% ReportLab generated PDF document -- digest (http://www.reportlab.com)\n\n/Info 5 0 R\n/Root 4 0 R\n/Size 8\n>>\nstartxref\n1031\n%%EOF\n' # noqa
        self.training_report = SimpleUploadedFile(name='training-report.pdf', content=pdf_content,
                                                  content_type='application/pdf')
        self.training_payload_valid = {
            'training_type': self.training_type_1.pk,
            'completion_report': self.training_report,
        }
        self.training_payload_invalid = {
            'training_type': self.training_type_2.pk,
            'completion_report': self.training_report,
        }

    def test_access_training_page_not_authenticated(self):
        response = self.client.get(self.training_url)

        self.assertRedirects(response, f'{self.login_url}?next={self.training_url}')

    def test_access_training_page_authenticated(self):
        self.client.force_login(user=self.user)

        response = self.client.get(self.training_url)

        self.assertEqual(response.status_code, 200)

    def test_submit_new_training_valid(self):
        self.client.force_login(user=self.user)

        response = self.client.post(self.training_url, self.training_payload_valid)
        messages = list(response.context['messages'])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level, msgs.SUCCESS)
        self.assertEqual(Training.objects.count(), 110)

    def test_submit_new_training_invalid(self):
        self.client.force_login(user=self.user)

        response = self.client.post(self.training_url, self.training_payload_invalid)
        messages = list(response.context['messages'])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level, msgs.ERROR)
        self.assertEqual(Training.objects.count(), 109)

    def test_view_training_not_authenticated(self):
        response = self.client.get(self.training_view_url)

        self.assertRedirects(response, f'{self.login_url}?next={self.training_view_url}')

    def test_view_training_authenticated(self):
        self.client.force_login(user=self.user)

        response = self.client.get(self.training_view_url)

        self.assertEqual(response.status_code, 200)

    def test_view_training_authenticated_as_other_user(self):
        self.client.force_login(user=self.admin)

        response = self.client.get(self.training_view_url)

        self.assertEqual(response.status_code, 404)

    def test_withdraw_training(self):
        self.client.force_login(user=self.user)

        response = self.client.post(self.training_view_url, {'withdraw': ''})
        messages = list(response.context['messages'])
        self.training.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.training.status, TrainingStatus.WITHDRAWN)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level, msgs.SUCCESS)

    def test_access_training_list(self):
        self.client.force_login(user=self.admin)

        response = self.client.get(self.console_training_url)

        self.assertEqual(response.status_code, 200)

    def test_accept_training_valid(self):
        self.client.force_login(user=self.admin)

        response = self.client.post(
            self.training_process_url, {**self.training_process_data, 'form-0-answer': ['True'], 'accept': ['']}
        )
        self.training.refresh_from_db()

        self.assertRedirects(response, self.console_training_url)
        self.assertEqual(self.training.status, TrainingStatus.ACCEPTED)

    @patch('console.services.get_info_from_certificate_pdf')
    def test_accept_training_invalid(self, mock_get_info_from_certificate_pdf):
        mock_get_info_from_certificate_pdf.return_value = {"Foo": "Bar"}
        self.client.force_login(user=self.admin)

        response = self.client.post(
            self.training_process_url, {**self.training_process_data, 'form-0-answer': ['False'], 'accept': ['']}
        )
        self.training.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.training.status, TrainingStatus.REVIEW)

    def test_reject_training_valid(self):
        self.client.force_login(user=self.admin)

        response = self.client.post(
            self.training_process_url,
            {**self.training_process_data, 'reject': [''], 'reviewer_comments': ['You have been rejected.']},
        )
        self.training.refresh_from_db()

        self.assertRedirects(response, self.console_training_url)
        self.assertEqual(self.training.status, TrainingStatus.REJECTED)

    @patch('console.services.get_info_from_certificate_pdf')
    def test_reject_training_invalid(self, mock_get_info_from_certificate_pdf):
        mock_get_info_from_certificate_pdf.return_value = {"Foo": "Bar"}
        self.client.force_login(user=self.admin)

        response = self.client.post(self.training_process_url, {**self.training_process_data, 'reject': ['']})
        self.training.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.training.status, TrainingStatus.REVIEW)
