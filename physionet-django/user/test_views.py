from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.views import (LoginView, LogoutView, PasswordChangeView, PasswordResetView,
    PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView)
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from user.forms import LoginForm, ResetPasswordForm, SetPasswordForm, EditPasswordForm
from user.models import User, AssociatedEmail
from user.management.commands.resetdb import load_fixture_profiles
from user.views import (activate_user, set_primary_email, set_public_emails,
    add_email, remove_email, edit_emails, edit_profile, edit_password_done,
    public_profile, register, user_home, user_settings, verify_email)

import pdb

# Add decorator to test invalid users



class TestMixin(object):
    """
    Mixin for test methods
    """
    def make_get_request(self, reverse_name):
        "Create and set a get request"
        self.get_request = self.factory.get(reverse(reverse_name))
        self.get_request.user = self.user

    def make_post_request(self, reverse_name, data):
        "Create and set a post request"
        self.post_request = self.factory.post(reverse(reverse_name), data)
        self.post_request.user = self.user

        # Provide the message object to the request because middleware
        # is not supported by RequestFactory
        setattr(self.post_request, 'session', 'session')
        messages = FallbackStorage(self.post_request)
        setattr(self.post_request, '_messages', messages)

    def run_get_request(self, view, status_code=200):
        "Test the get request with the view against the expected status code"
        response = view(self.get_request)
        self.assertEqual(response.status_code, status_code)

    def run_post_request(self, view, status_code=200, redirect_name=None):
        "Test the post request with the view against the expected status code"
        response = view(self.post_request)
        self.assertEqual(response.status_code, status_code)

        if status_code == 302:
            self.assertRedirects(response, reverse(redirect_name))


class TestAuthViews(TestCase, TestMixin):
    """
    Test views that require authentication
    """
    fixtures = ['user']

    def setUp(self):
        load_fixture_profiles()
        self.factory = RequestFactory()
        self.user = User.objects.get(email='rgmark@mit.edu')
        self.anonymous_user = AnonymousUser()

    


    def test_user_home(self):
        self.make_get_request('user_home')
        self.run_get_request(user_home)

    def test_edit_profile(self):
        self.make_get_request('edit_profile')
        self.run_get_request(edit_profile)

        self.make_post_request('edit_profile',
            data={'first_name': 'Roger', 'last_name': 'Federer'})
        self.run_post_request(edit_profile)


    # Do we even have to test these inbuilt shit?
    # def test_edit_password(self):

    #     old_password = self.user.password

    #     # The view function
    #     edit_password = PasswordChangeView.as_view(
    #         form_class=EditPasswordForm,
    #         success_url = reverse('edit_password_done'),
    #         template_name='user/edit_password.html',
    #     )

    #     self.make_get_request('edit_password')
    #     self.run_get_request(edit_password)

    #     self.make_post_request('edit_password',
    #         data={'old_password':'Tester1!', 'new_password1':'Very5trongt0t@11y',
    #         'new_password2':'Very5trongt0t@11y'})

    #     pdb.set_trace()
    #     self.run_post_request(edit_password, 302)

    #     print('really!')

        # response = self.client.post(reverse('edit_password'), data={'old_password':'Tester1!', 'new_password1':'lol', 'new_password2':'haha'})
        # print(response.status_code)
        # pdb.set_trace()
        # self.assertEqual(old_password, self.user.password)
        # print('yep')

        # response = self.client.post(reverse('edit_password'), data={'old_password':'Tester1!', 'new_password1':'IJEAFINilhae81324', 'new_password2':'IJEAFINilhae81324'})

        # pdb.set_trace()
        # self.assertEqual(old_password, self.user.password)
        # print('yep')

        # Old
        #pbkdf2_sha256$36000$Zj28MDwT3xxY$zQgpJUJisgQkgt364G+xi4ip7T4lRGjs6P1OzVmJkBc=

        #pbkdf2_sha256$36000$Zj28MDwT3xxY$zQgpJUJisgQkgt364G+xi4ip7T4lRGjs6P1OzVmJkBc=

        #pbkdf2_sha256$36000$Zj28MDwT3xxY$zQgpJUJisgQkgt364G+xi4ip7T4lRGjs6P1OzVmJkBc=


    def test_emails(self):
        """
        Test email changing functionality
        """

        user = User.objects.get(email='tester@mit.edu')

        # Change primary email
        secondary_email = AssociatedEmail.objects.filter(user=user,
            is_primary_email=False).first()
        user.email = secondary_email.email
        user.save(update_fields=['email'])
        new_primary_email = AssociatedEmail.objects.get(email=secondary_email.email)

        self.assertTrue(new_primary_email.is_primary_email)

    def test_admin_home(self):
        """
        Test that the admin page redirects to a login page.
        """
        response = self.client.get('/admin/')
        redirect_url = response['Location'].split('?')[0]

        self.assertEqual('/admin/login/', redirect_url)
        self.assertEqual(302, response.status_code)
        self.assertRedirects(response,'/admin/login/?next=/admin/',
            status_code=302)

# def test_forms(self):
#         response = self.client.post("/my/form/", {'something':'something'})
#         self.assertFormError(response, 'form', 'something', 'This field is required.')



class TestPublicViews(TestCase, TestMixin):
    "Test views that do not require authentication"

    fixtures = ['user']

    def setUp(self):
        load_fixture_profiles()
        self.factory = RequestFactory()
        self.user = AnonymousUser()

    # def test_public_pages(self):
    #     """
    #     Test that public pages are reached and return '200' codes.
    #     """
    #     response = self.client.get(reverse('home'))
    #     self.assertEqual(200, response.status_code)

    def test_register(self):
        self.make_get_request('register')
        self.run_get_request(register, 200)
        print('No fucking redirect!')

        self.make_post_request('register',
            data={'email':'jackreacher@mit.edu', 'first_name': 'Jack', 'last_name': 'Reacher','password1':'Very5trongt0t@11y', 'password2':'Very5trongt0t@11y'})
        # Recall that register uses same view upon success, so not 302
        self.run_post_request(register, 200)
        # Check user object was created
        self.assertIsNotNone(User.objects.filter(email='jackreacher@mit.edu'))