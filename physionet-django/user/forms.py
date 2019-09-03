import os
import pdb

from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import password_validation
from django.core.files.uploadedfile import UploadedFile
from django.core.validators import EmailValidator
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy
from django.db import transaction

from project.models import PublishedProject
from user.models import AssociatedEmail, User, Profile, CredentialApplication, CloudInformation
from user.widgets import ProfilePhotoInput
from user.validators import UsernameValidator, validate_name


class AssociatedEmailChoiceForm(forms.Form):
    """
    For letting users choose one of their AssociatedEmails.
    E.g. primary email, public email, corresponding email
    """
    associated_email = forms.ModelChoiceField(queryset=None, to_field_name='email',
        label='Email')

    def __init__(self, user, selection_type, author=None, *args, **kwargs):
        # Email choices are those belonging to a user
        super(AssociatedEmailChoiceForm, self).__init__(*args, **kwargs)

        associated_emails = user.associated_emails.filter(is_verified=True).order_by('-is_primary_email')
        self.fields['associated_email'].queryset = associated_emails

        if selection_type == 'primary':
            self.fields['associated_email'].empty_label = None
            self.fields['associated_email'].initial = associated_emails.filter(
                is_primary_email=True).first()
        elif selection_type == 'public':
            # This might be None
            self.fields['associated_email'].initial = associated_emails.filter(
                is_public=True).first()
            self.fields['associated_email'].required = False
        elif selection_type == 'corresponding':
            self.fields['associated_email'].empty_label = None
            self.fields['associated_email'].initial = author.corresponding_email


class AddEmailForm(forms.ModelForm):
    """
    For adding new associated emails
    """
    class Meta:
        model = AssociatedEmail
        fields = ('email',)
        widgets = {
            'email':forms.EmailInput(attrs={'class': 'form-control dropemail',
                'validators':[EmailValidator]}),
        }

    def clean_email(self):
        """
        Check that the email is unique for the user. Make the email
        lowercase
        """
        data = self.cleaned_data['email'].lower()

        if AssociatedEmail.objects.filter(email=data).exists():
            raise forms.ValidationError(
                'The email is already registered')

        return data


class LoginForm(auth_forms.AuthenticationForm):
    """
    Form for logging in.
    """
    username = auth_forms.UsernameField(
        label='Email or Username',
        max_length=254,
        widget=forms.TextInput(attrs={'autofocus': True, 'class': 'form-control',
            'placeholder': 'Email or Username'}),
    )
    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control',
            'placeholder': 'Password'}),
    )

    remember = forms.BooleanField(label='Remember Me', required=False)

    error_messages = {
        'invalid_login': ugettext_lazy(
            "Please enter a correct username/email and password. Note that the password "
            "field is case-sensitive."
        ),
        'inactive': ugettext_lazy("This account has not been activated. Please check your "
            "email for the activation link."),
    }



class UserChangeForm(forms.ModelForm):
    """A form for updating user objects in the admin interface. Includes all
    fields on the user, but replaces the password field with the password hash
    display field. Use the admin interface to change passwords.
    """
    password = auth_forms.ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = ('email', 'password', 'is_active', 'is_admin')

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial["password"]

class UsernameChangeForm(forms.ModelForm):
    """
    Updating the username filed
    """

    class Meta:
        model = User
        fields = ('username',)
        widgets = {
            'username':forms.TextInput(attrs={'class': 'form-control', 'validators':[UsernameValidator]}),
        }

    def clean_username(self):
        "Record the original username in case it is needed"
        self.old_username = self.instance.username
        self.old_file_root = self.instance.file_root()
        if User.objects.filter(username__iexact=self.cleaned_data['username']):
            raise forms.ValidationError("A user with that username already exists.")
        return self.cleaned_data['username']

    def save(self):
        """
        Change the media file directory name and photo name if any,
        to match the new username
        """
        new_username = self.cleaned_data['username']

        if self.old_username != new_username:
            with transaction.atomic():
                super().save()
                profile = self.instance.profile
                if profile.photo:
                    name_components = profile.photo.name.split('/')
                    name_components[1] = new_username
                    profile.photo.name = '/'.join(name_components)
                    profile.save()
                if os.path.exists(self.old_file_root):
                    os.rename(self.old_file_root, self.instance.file_root())


class ProfileForm(forms.ModelForm):
    """
    For editing the profile
    """
    photo = forms.ImageField(required=False, widget=ProfilePhotoInput(
        attrs={'template_name': 'user/profile_photo_input.html'}))

    class Meta:
        model = Profile
        fields = ('first_names', 'last_name', 'affiliation',
                  'location', 'website', 'photo')

    def clean_photo(self):
        data = self.cleaned_data['photo']
        # Check size if file is being uploaded
        if data and isinstance(data, UploadedFile):
            if data.size > Profile.MAX_PHOTO_SIZE:
                raise forms.ValidationError('Exceeded maximum size: {0}'.format(Profile.MAX_PHOTO_SIZE))
        # Save the existing file path in case it needs to be deleted.
        # After is_valid runs, the instance photo is already updated.
        if self.instance.photo:
            self.old_photo_path = self.instance.photo.path

        return data

    def save(self):
        # Delete the old photo if the user is uploading a new photo, and
        # they already had one (before saving the new photo)
        if 'photo' in self.changed_data and hasattr(self, 'old_photo_path'):
            os.remove(self.old_photo_path)
        super(ProfileForm, self).save()


class RegistrationForm(forms.ModelForm):
    """A form for creating new users. Includes all the required
    fields, plus a repeated password.
    """

    first_names = forms.CharField(max_length=100, label='First Names',
                    widget=forms.TextInput(attrs={'class': 'form-control'}),
                    validators=[validate_name])
    last_name = forms.CharField(max_length=50, label='Last Name',
                    widget=forms.TextInput(attrs={'class': 'form-control'}),
                    validators=[validate_name])
    password1 = forms.CharField(label='Password',
                    widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    password2 = forms.CharField(label='Password Confirmation',
                    widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ('email','username',)
        widgets = {
            'email':forms.EmailInput(attrs={'class': 'form-control dropemail',
                'validators':[EmailValidator]}),
            'username':forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_username(self):
        "Record the original username in case it is needed"
        if User.objects.filter(username__iexact=self.cleaned_data['username']):
            raise forms.ValidationError("A user with that username already exists.")
        return self.cleaned_data['username']


    def clean_password2(self):
        # Check that the two password entries match
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The passwords don't match")

        # Note: if any of the following fields are missing, the form
        # should ultimately be rejected, but we want to go ahead and
        # check the password anyway
        self.instance.username = self.cleaned_data.get('username', '')
        self.instance.first_names = self.cleaned_data.get('first_names', '')
        self.instance.last_name = self.cleaned_data.get('last_name', '')
        self.instance.email = self.cleaned_data.get('email', '')
        password_validation.validate_password(self.cleaned_data.get('password2'),
            self.instance)
        return password2


    def save(self):
        # Save the provided password in hashed format

        if self.errors: return

        user = super(RegistrationForm, self).save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.email = user.email.lower()

        with transaction.atomic():
            user.save()
            # Save additional fields in Profile model
            profile = Profile.objects.create(user=user,
                first_names=self.cleaned_data['first_names'],
                last_name=self.cleaned_data['last_name'])
        return user


# Split the credential application forms into multiple forms
class PersonalCAF(forms.ModelForm):
    """
    Credential application form personal attributes
    """
    class Meta:
        model = CredentialApplication
        fields = ('first_names', 'last_name', 'suffix', 'researcher_category',
            'organization_name', 'job_title', 'city', 'state_province',
            'zip_code', 'country', 'webpage')
        help_texts = {
            'first_names': 'First (given) name.',
            'last_name': "Last (family) name.",
            'suffix': """Please leave the suffix blank if your name does not 
                include a suffix like 'Jr.' or 'III'. Do not list degrees. 
                Do not put a prefix like 'Mr' or 'Ms'. Do not put 'not 
                applicable'. Especially, do not leave a string of digits from 
                browser autofill.""",
            'researcher_category': "Your research status.",
            'organization_name': """Your employer or primary affiliation. 
                Put 'None' if you are an independent researcher.""",
            'job_title': """Your job title or position (e.g., student) within 
                your institution or organization.""",
            'city': "The city where you live.",
            'state_province': 'The state or province where you live.',
            'zip_code': "The zip code of the city where you live.",
            'country': 'The country where you live.',
            'webpage': """Your organization's webpage. If possible, please 
                include a link to a webpage with your biography or other 
                personal details.""",
            'research_summary': """Brief description on your research. If you 
                will be using the data for a class, please include course name 
                and number in your description.""",
        }
        widgets = {
           'research_summary': forms.Textarea(attrs={'rows': 3}),
           'suffix': forms.TextInput(attrs={'autocomplete': 'off'}),
        }
        labels = {
            'state_province': 'State/Province',
            'first_names': 'My first (given) name(s)',
            'last_name': 'My last (family) name(s)',
            'suffix': 'Suffix, if applicable:',
            'job_title': 'Job title or position',
            'zip_code': 'ZIP/postal code'
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = user.profile

        self.initial = {'first_names':self.profile.first_names,
            'last_name':self.profile.last_name,
            'organization_name':self.profile.affiliation,
            'webpage':self.profile.website}


class ResearchCAF(forms.ModelForm):
    """
    Credential application form research attributes
    """
    class Meta:
        model = CredentialApplication
        fields = ('research_summary',)
        help_texts = {
            'research_summary': """Brief description on your research. If you 
                will be using the data for a class, please include course name 
                and number in your description.""",
        }
        widgets = {
           'research_summary': forms.Textarea(attrs={'rows': 2}),
        }

        labels = {
            'research_summary': 'Research Topic'
        }


class TrainingCAF(forms.ModelForm):
    """
    Credential application form training course attributes
    """
    class Meta:
        model = CredentialApplication
        fields = ('training_completion_report',)
        help_texts = {
            'training_completion_report': """Upload the completion report from 
                the CITI 'Data or Specimens Only Research' training program 
                (PDF or image file). The completion report lists all modules 
                completed, with dates and scores. Do NOT upload the completion 
                certificate. If you would like to submit multiple pages, please 
                combine them into a single pdf file.""",
        }


class ReferenceCAF(forms.ModelForm):
    """
    Credential application form reference attributes
    """
    class Meta:
        model = CredentialApplication
        fields = ('reference_category', 'reference_name',
            'reference_email', 'reference_title')
        help_texts = {
            'reference_category': """Your reference's relationship to you. If 
                you are a student or postdoc, this must be your supervisor.""",
            'reference_name': 'The full name of your reference.',
            'reference_email': 'The email address of your reference.',
            'reference_title': "Your reference's professional title or position."
        }
        labels = {
            'reference_title': 'Reference job title or position'
        }


class CredentialApplicationForm(forms.ModelForm):
    """
    Form to apply for PhysioNet credentialling
    """
    class Meta:
        model = CredentialApplication
        fields = (
            # Personal
            'first_names', 'last_name', 'suffix', 'researcher_category',
            'organization_name', 'job_title', 'city', 'state_province',
            'zip_code', 'country', 'webpage',
            # Training course
            'training_course_name', 'training_completion_date',
            'training_completion_report',
            # Reference
            'reference_category', 'reference_name',
            'reference_email', 'reference_title',
            # Research area
            'research_summary')


    def __init__(self, user, *args, **kwargs):
        """
        This form is only for processing post requests.
        """
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = user.profile


    def clean(self):
        data = self.cleaned_data

        if any(self.errors):
            return

        # Students and postdocs must provide their supervisor as a reference
        if data['researcher_category'] in [0, 1] and data['reference_category'] != 0:
            raise forms.ValidationError('If you are a student or postdoc, you must provide your supervisor as a reference.')

        if not self.instance and CredentialApplication.objects.filter(user=self.user, status=0):
            raise forms.ValidationError('Outstanding application exists.')

    def save(self):
        credential_application = super().save(commit=False)
        slug = get_random_string(20)
        while CredentialApplication.objects.filter(slug=slug):
            slug = get_random_string(20)
        credential_application.user = self.user
        credential_application.slug = slug
        credential_application.save()
        return credential_application


class CredentialReferenceForm(forms.ModelForm):
    """
    Form to apply for PhysioNet credentialling. The name must match.
    """
    class Meta:
        model = CredentialApplication
        fields = ('reference_response', 'reference_response_text')
        labels = {
            'reference_response': 'I am familiar with the research and support this request.',
            'reference_response_text': 'Please briefly describe your working relationship with the applicant.'
        }
        widgets = {
            'reference_response_text':forms.Textarea(attrs={'rows': 3}),
        }

    def save(self):
        """
        Process the decision
        """
        application = super().save(commit=False)

        # Deny
        if self.cleaned_data['reference_response'] == 1:
            application.status = 1

        application.reference_response_datetime = timezone.now()
        application.reference_response_text = self.cleaned_data['reference_response_text']
        application.save()
        return application


class ContactForm(forms.Form):
    """
    For contacting PhysioNet support
    """
    name = forms.CharField(max_length=100, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Name *'}))
    email = forms.EmailField(max_length=100, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Email *'}))
    subject = forms.CharField(max_length=100, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Subject *'}))
    message = forms.CharField(max_length=2000, widget=forms.Textarea(
        attrs={'class': 'form-control', 'placeholder': 'Message *'}))

class CloudForm(forms.ModelForm):
    """
    Form to store the AWS ID, and point to the google GCP email.
    """
    class Meta:
        model = CloudInformation
        fields = ('gcp_email','aws_id',)
        labels = {
            'gcp_email': 'GCP Email',
            'aws_id': 'AWS ID',
        }
    def __init__(self, *args, **kwargs):
        # Email choices are those belonging to a user
        super().__init__(*args, **kwargs)
        associated_emails = self.instance.user.associated_emails.filter(is_verified=True)
        self.fields['gcp_email'].queryset = associated_emails
        self.fields['gcp_email'].required = False
