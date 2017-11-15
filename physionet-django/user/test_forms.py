from django.test import TestCase
from django.urls import reverse

from user.forms import (AssociatedEmailChoiceForm, AssociatedEmailForm,
    EditPasswordForm, LoginForm, ProfileForm, ResetPasswordForm, SetPasswordForm,
    UserCreationForm)
from user.management.commands.resetdb import load_fixture_profiles
from user.models import User


class TestForms(TestCase):

    fixtures = ['user']

    def setUp(self):
        load_fixture_profiles()
    
    def create_test_forms(self, FormClass, valid_dict, invalid_dict, user=None):
        """
        Helper method to create a valid and invalid form of a certain form class.
        Some forms require the user object
        """
        if user:
            self.valid_form = FormClass(user=user, data=valid_dict)
            self.invalid_form = FormClass(user=user, data=invalid_dict)
        else:
            self.valid_form = FormClass(data=valid_dict)
            self.invalid_form = FormClass(data=invalid_dict)


    def run_test_forms(self, invalid_form_errors):
        """
        Helper method to test the valid form and an invalid form.
        Input the expected form error of the invalid form.

        Remember, this method name cannot begin with 'test'
        """
        self.assertTrue(self.valid_form.is_valid())
        self.assertFalse(self.invalid_form.is_valid())
        self.assertEqual(self.invalid_form.errors, invalid_form_errors)

    def test_associated_email_choice_form(self):
        """
        Choice field in form, cannot use create helper function
        """
        user = User.objects.get(email='tester@mit.edu')
        self.valid_form = AssociatedEmailChoiceForm(user=user,
            include_primary=True, data={'associated_email':'tester2@mit.edu'})
        self.invalid_form = AssociatedEmailChoiceForm(user=user,
            include_primary=True, data={'associated_email':'nonexistent@mit.edu'})
        self.run_test_forms({'associated_email':['Select a valid choice. That choice is not one of the available choices.']})

    def test_associated_email_form(self):
        self.create_test_forms(AssociatedEmailForm, {'email':'tester0@mit.edu'},
            {'email':'nonexistent'})
        self.run_test_forms({'email': ['Enter a valid email address.']})

    def test_edit_password_form(self):
        user = User.objects.get(email='tester@mit.edu')
        self.create_test_forms(EditPasswordForm, {'old_password':'Tester1!',
            'new_password1':'Very5trongt0t@11y', 'new_password2':'Very5trongt0t@11y'},
            {'old_password':'Tester1!',
            'new_password1':'weak', 'new_password2':'weak1'}, user=user)
        self.run_test_forms({'new_password2':["The two password fields didn't match."]})

    def test_login_form(self):
        self.create_test_forms(LoginForm, {'username':'tester@mit.edu','password':'Tester1!'},
            {'username':'tester@mit.edu', 'password':'wrong'})
        self.run_test_forms({'__all__':['Please enter a correct email and password. Note that both fields may be case-sensitive.']})

    def test_profile_form(self):
        self.create_test_forms(ProfileForm, {'first_name':'Tester',
            'middle_names':'Mid', 'last_name':'Bot',
            'url':'http://physionet.org'},
            {'first_name':'Tester','middle_names':'Mid',
            'last_name':'', 'phone':'0'})
        self.run_test_forms({'last_name': ['This field is required.']})

    def test_reset_password_form(self):
        self.create_test_forms(ResetPasswordForm, {'email':'tester@mit.edu'},
            {'email':'nonexistent'})
        self.run_test_forms({'email': ['Enter a valid email address.']})

    def test_set_password_form(self):
        user = User.objects.get(email='tester@mit.edu')
        self.create_test_forms(SetPasswordForm, {
            'new_password1':'Very5trongt0t@11y',
            'new_password2':'Very5trongt0t@11y'},
            {'new_password1':'weak', 'new_password2':'weak'}, user=user)
        self.run_test_forms(
            {'new_password2':['This password is too short. It must contain at least 8 characters.',
            'This password is too weak.']})

    def test_user_creation_form(self):
        self.create_test_forms(UserCreationForm, {'email':'tester0@mit.edu',
            'first_name':'Tester', 'middle_names':'Mid', 'last_name':'Bot',
            'password1':'Very5trongt0t@11y', 'password2':'Very5trongt0t@11y'},
            {'email':'tester0@mit.edu', 'first_name':'', 'middle_names':'Mid',
            'last_name':'Bot', 'password1':'weakweak', 'password2':'weakweak'})
        self.run_test_forms({'first_name':['This field is required.'],
            'password2':['This password is too weak.']})
