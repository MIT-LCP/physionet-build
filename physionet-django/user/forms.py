import os
import pdb

from django import forms
from django.conf import settings
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import password_validation
from django.core.files.uploadedfile import UploadedFile
from django.forms.widgets import FileInput
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import ugettext_lazy
from django.db import transaction

from physionet.aws import s3_mv_object, s3_mv_folder
from user.models import AssociatedEmail, User, Profile, CredentialApplication, CloudInformation
from user.trainingreport import (find_training_report_url,
                                 TrainingCertificateError)
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
            'email': forms.EmailInput(
                attrs={'class': 'form-control dropemail'}),
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
        self.old_file_root = self.instance.file_root(relative=(settings.STORAGE_TYPE == 'S3'))

        if User.objects.filter(username__iexact=self.cleaned_data['username']):
            raise forms.ValidationError("A user with that username already exists.")
        return self.cleaned_data['username'].lower()

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

                if settings.STORAGE_TYPE == 'S3':
                    s3_mv_folder(settings.AWS_STORAGE_BUCKET_NAME,
                        self.old_file_root, self.instance.file_root(relative=True))
                    return

                if os.path.exists(self.old_file_root):
                    os.rename(self.old_file_root, self.instance.file_root(relative=False))


class SaferImageField(forms.ImageField):
    """
    A field for uploaded image files.

    This wraps Django's django.forms.fields.ImageField (not to be
    confused with django.db.models.fields.files.ImageField!)

    When a file is uploaded, it is required to be a valid JPEG or PNG
    image file.  The filename specified by the client is ignored; the
    file is renamed to either 'image.png' or 'image.jpg' according to
    the detected type.

    The type is enforced both by checking the magic number before
    passing the file to ImageField.to_python (which invokes
    PIL.Image.open), and by checking the content type that Pillow
    reports.

    Since we check the magic number before calling PIL.Image.open,
    this means we avoid calling many of the possible image format
    parsers, which are historically sources of countless security
    bugs.

    Note, however, that this does not avoid calling *all* undesired
    parsers.  If one parser fails, then Pillow will try again with the
    next one in the list.  Most of the Pillow parsers will immediately
    reject files that don't start with an appropriate magic number,
    but some parsers may not.
    """

    ACCEPT_TYPES = ['image/jpeg', 'image/png']

    TYPE_SUFFIX = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
    }

    TYPE_SIGNATURE = {
        'image/jpeg': b'\xff\xd8',
        'image/png': b'\x89PNG\x0d\x0a\x1a\x0a',
    }

    def to_python(self, data):
        if data in self.empty_values:
            return None

        if hasattr(data, 'temporary_file_path'):
            path = data.temporary_file_path()
            with open(path, 'rb') as f:
                signature = f.read(16)
        else:
            signature = data.read(16)
            data.seek(0)

        for content_type in self.ACCEPT_TYPES:
            if signature.startswith(self.TYPE_SIGNATURE[content_type]):
                break
        else:
            raise forms.ValidationError('Not a valid JPEG or PNG image file.')

        result = super().to_python(data)

        # check that the content type is what we expected
        if result.content_type != content_type:
            raise forms.ValidationError('Not a valid JPEG or PNG image file.')

        # set the name according to the content type
        result.name = 'image' + self.TYPE_SUFFIX[content_type]
        return result

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        if isinstance(widget, FileInput):
            attrs['accept'] = ','.join(self.ACCEPT_TYPES)
        return attrs


class ProfileForm(forms.ModelForm):
    """
    For editing the profile
    """
    photo = SaferImageField(required=False, widget=ProfilePhotoInput(
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

    class Meta:
        model = User
        fields = ('email','username',)
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_username(self):
        "Record the original username in case it is needed"
        if User.objects.filter(username__iexact=self.cleaned_data['username']):
            raise forms.ValidationError("A user with that username already exists.")
        return self.cleaned_data['username'].lower()

    def save(self):
        """
        Process the registration form
        """
        if self.errors:
            return

        user = super(RegistrationForm, self).save(commit=False)
        user.email = user.email.lower()

        with transaction.atomic():
            user.save()
            # Save additional fields in Profile model
            Profile.objects.create(user=user,
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
            'first_names': """Your first name(s). This can be edited in your
                profile settings.""",
            'last_name': """Your last (family) name. This can be edited in
                your profile settings.""",
            'suffix': """Please leave the suffix blank if your name does not
                include a suffix like "Jr." or "III". Do not list degrees.
                Do not put a prefix like "Mr" or "Ms". Do not put "not
                applicable".""",
            'researcher_category': "Your research status.",
            'organization_name': """Your employer or primary affiliation.
                Put "None" if you are an independent researcher.""",
            'job_title': """Your job title or position (e.g., student) within
                your institution or organization.""",
            'city': "The city where you live.",
            'state_province': "The state or province where you live. (Required for residents of Canada or the US.)",
            'zip_code': "The zip code of the city where you live.",
            'country': "The country where you live.",
            'webpage': """Please include a link to a webpage with your
                biography or other personal details (ORCID, LinkedIn,
                Github, etc.).""",
            'research_summary': """Brief description of your proposed research.
                If you will be using the data for a class, please include
                course name and number in your description.""",
        }
        widgets = {
           'research_summary': forms.Textarea(attrs={'rows': 3}),
           'suffix': forms.TextInput(attrs={'autocomplete': 'off'}),
        }
        labels = {
            'state_province': 'State/Province',
            'first_names': 'First (given) name(s)',
            'last_name': 'Last (family) name(s)',
            'suffix': 'Suffix, if applicable:',
            'job_title': 'Job title or position',
            'zip_code': 'ZIP/postal code'
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = user.profile
        self.fields['first_names'].disabled = True
        self.fields['last_name'].disabled = True

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
            'research_summary': """Brief description of your research. If you
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
            'training_completion_report': """Do not upload the completion
                certificate. Upload the completion report from the CITI
                'Data or Specimens Only Research' training program which
                lists all modules completed, with dates and scores.
                Expired reports will not be accepted.""",
        }

    def clean_training_completion_report(self):
        reportfile = self.cleaned_data['training_completion_report']
        if reportfile and isinstance(reportfile, UploadedFile):
            if reportfile.size > CredentialApplication.MAX_REPORT_SIZE:
                raise forms.ValidationError(
                    'Completion report exceeds size limit')
        return reportfile


class ReferenceCAF(forms.ModelForm):
    """
    Credential application form reference attributes
    """
    class Meta:
        model = CredentialApplication
        fields = ('reference_category', 'reference_name',
            'reference_email', 'reference_organization', 'reference_title')
        help_texts = {
            'reference_category': """Your reference's relationship to you. If
                you are a student or postdoc, this must be your supervisor.
                Otherwise, you may list a colleague. Do not list yourself
                or another student as reference. Remind your reference to
                respond promptly, as long response times will prevent approval
                of your application.""",
            'reference_name': 'The full name of your reference.',
            'reference_email': """The email address of your reference. It is
                strongly recommended that this be an institutional email address.""",
            'reference_organization': """Your reference's employer or primary
                affiliation.""",
            'reference_title': "Your reference's professional title or position."
        }
        labels = {
            'reference_title': 'Reference job title or position'
        }

    def __init__(self, user, *args, **kwargs):
        """
        This form is only for processing post requests.
        """
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_reference_name(self):
        reference_name = self.cleaned_data.get('reference_name')
        if reference_name:
            return reference_name.strip()

    def clean_reference_email(self):
        reference_email = self.cleaned_data.get('reference_email')
        if reference_email:
            if reference_email in self.user.get_emails():
                raise forms.ValidationError("""You can not put yourself
                    as a reference.""")
            else:
                return reference_email.strip()

    def clean_reference_title(self):
        reference_title = self.cleaned_data.get('reference_title')
        if reference_title:
            return reference_title.strip()


class CredentialApplicationForm(forms.ModelForm):
    """
    Form to apply for credentialling
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
            'reference_category', 'reference_name', 'reference_email',
            'reference_organization', 'reference_title',
            # Research area
            'research_summary')

    def __init__(self, user, *args, **kwargs):
        """
        This form is only for processing post requests.
        """
        super().__init__(*args, **kwargs)
        self.user = user
        self.profile = user.profile
        self.fields['first_names'].disabled = True
        self.fields['last_name'].disabled = True
        self.initial = {'first_names': self.profile.first_names,
                        'last_name': self.profile.last_name}

    def clean(self):
        data = self.cleaned_data

        if any(self.errors):
            return

        ref_details = [data['reference_category'] is not None,
                       data['reference_name'],
                       data['reference_email'],
                       data['reference_organization'],
                       data['reference_title']]

        ref_required = data['researcher_category'] in [0, 1, 6, 7]
        supervisor_required = data['researcher_category'] in [0, 1, 7]
        state_required = data['country'] in ['US', 'CA']

        # Students and postdocs must provide their supervisor as a reference
        if supervisor_required and data['reference_category'] != 0:
            raise forms.ValidationError("""If you are a student or postdoc,
                you must provide your supervisor as a reference.""")

        # Check the full reference details are provided if appropriate
        if ref_required and not all(ref_details):
            raise forms.ValidationError("""A reference is required. Please
                provide full contact details, including a reference
                category.""")

        # if any reference fields are add, all fields must be completed
        if any(ref_details) and not all(ref_details):
            raise forms.ValidationError("""Please provide full details for your
                reference, including the reference category.""")

        # If applicant is from USA or Canada, the state must be provided
        if state_required and not data['state_province']:
            raise forms.ValidationError("Please add your state or province.")

        if not self.instance and CredentialApplication.objects.filter(user=self.user, status=0):
            raise forms.ValidationError('Outstanding application exists.')

        # Check for a recognized CITI verification link.
        try:
            reportfile = data['training_completion_report']
            self.report_url = find_training_report_url(reportfile)
        except TrainingCertificateError:
            raise forms.ValidationError(
                'Please upload the "Completion Report" file, '
                'not the "Completion Certificate".')

    def save(self):
        credential_application = super().save(commit=False)
        slug = get_random_string(20)
        while CredentialApplication.objects.filter(slug=slug):
            slug = get_random_string(20)
        credential_application.user = self.user
        credential_application.slug = slug
        credential_application.training_completion_report_url = self.report_url
        credential_application.save()
        return credential_application


class CredentialReferenceForm(forms.ModelForm):
    """
    Form to apply for credentialling. The name must match.
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
    For contacting support
    """
    name = forms.CharField(max_length=100, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Name *'}))
    email = forms.EmailField(max_length=100, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Email *'}))
    subject = forms.CharField(max_length=100, widget=forms.TextInput(
        attrs={'class': 'form-control', 'placeholder': 'Subject *'}))
    message = forms.CharField(max_length=2000, widget=forms.Textarea(
        attrs={'class': 'form-control', 'placeholder': 'Message *'}))

    def clean_email(self):
        # Disallow addresses that look like they come from this machine.
        addr = self.cleaned_data['email'].lower()
        for domain in settings.EMAIL_FROM_DOMAINS:
            if addr.endswith('@' + domain) or addr.endswith('.' + domain):
                raise forms.ValidationError('Please enter your email address.')
        return self.cleaned_data['email']

class CloudForm(forms.ModelForm):
    """
    Form to store the AWS ID, and point to the google GCP email.
    """
    class Meta:
        model = CloudInformation
        fields = ('gcp_email','aws_id',)
        labels = {
            'gcp_email': 'Google (Email)',
            'aws_id': 'Amazon (ID)',
        }
    def __init__(self, *args, **kwargs):
        # Email choices are those belonging to a user
        super().__init__(*args, **kwargs)
        associated_emails = self.instance.user.associated_emails.filter(is_verified=True)
        self.fields['gcp_email'].queryset = associated_emails
        self.fields['gcp_email'].required = False


# class ActivationForm(forms.ModelForm):
class ActivationForm(forms.Form):
    """A form for creating new users. Includes all the required
    fields, plus a repeated password.
    """
    username = forms.CharField(disabled=True, widget=forms.TextInput(attrs={
        'class': 'form-control'}))
    email = forms.EmailField(disabled=True, widget=forms.TextInput(attrs={
        'class': 'form-control'}))
    password1 = forms.CharField(label='Password',
                    widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    password2 = forms.CharField(label='Password Confirmation',
                    widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def __init__(self, user, *args, **kwargs):
        """
        This form is only for processing post requests.
        """
        super().__init__(*args, **kwargs)
        self.fields['username'].initial = user.username
        self.fields['email'].initial = user.email
        self.user = user

    def clean_password2(self):
        # Check that the two password entries match
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The passwords don't match")

        password_validation.validate_password(
            self.cleaned_data.get('password1'), user=self.user)

        return password1
