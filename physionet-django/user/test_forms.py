from django.test import TestCase
from django.urls import reverse

from user.forms import (AssociatedEmailChoiceForm, AddEmailForm,
    LoginForm, ProfileForm, RegistrationForm)
from user.models import User


class TestForms(TestCase):
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
        user = User.objects.get(email='admin@mit.edu')
        self.valid_form = AssociatedEmailChoiceForm(user=user,
            selection_type='primary', data={'associated_email':'admin2@mit.edu'})
        self.invalid_form = AssociatedEmailChoiceForm(user=user,
            selection_type='public', data={'associated_email':'nonexistent@mit.edu'})
        self.run_test_forms({'associated_email':['Select a valid choice. That choice is not one of the available choices.']})

    def test_associated_email_form(self):
        self.create_test_forms(AddEmailForm, {'email':'tester0@mit.edu'},
            {'email':'nonexistent'})
        self.run_test_forms({'email': ['Enter a valid email address.']})

    def test_login_form(self):
        self.create_test_forms(LoginForm, {'username':'admin','password':'Tester11!'},
            {'username':'admin', 'password':'wrong'})
        self.run_test_forms({'__all__':['Please enter a correct username/email and password. Note that the password field is case-sensitive.']})

    def test_profile_form(self):
        self.create_test_forms(ProfileForm, {'first_names':'Tester Mid',
            'last_name':'Bot',
            'url':'http://physionet.org'},
            {'first_names':'Tester Mid',
            'last_name':'', 'phone':'0'})
        self.run_test_forms({'last_name': ['This field is required.']})

    def test_user_creation_form(self):
        self.create_test_forms(RegistrationForm, {'email': 'tester0@mit.edu',
                                                  'username': 'The-Tester', 'first_names': 'Tester Mid',
                                                  'last_name': 'Bot', 'privacy_policy': 'True'},
                                                 {'email': 'tester0@mit.edu',
                                                  'username': 'bot-net', 'first_names': '',
                                                  'last_name': 'Bot', 'privacy_policy': 'True'})
        self.run_test_forms({'first_names': ['This field is required.']})

    def test_privacy_policy_user_creation_form(self):
        self.create_test_forms(RegistrationForm, {'email': 'tester0@mit.edu',
                                                  'username': 'The-Tester', 'first_names': 'Tester Mid',
                                                  'last_name': 'Bot', 'privacy_policy': 'True'},
                                                 {'email': 'tester0@mit.edu',
                                                  'username': 'The-Tester', 'first_names': 'Tester Mid',
                                                  'last_name': 'Bot', 'privacy_policy': 'False'})

        self.run_test_forms({'privacy_policy': ['This field is required.']})
