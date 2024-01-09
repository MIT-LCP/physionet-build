import datetime
import time

from django import forms
from django.conf import settings
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import password_validation
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import F, Q
from django.forms.widgets import FileInput
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.html import mark_safe
from django.utils.translation import gettext_lazy
from physionet.utility import validate_pdf_file_type
from user.models import (
    AssociatedEmail,
    CloudInformation,
    CredentialApplication,
    Profile,
    User,
    Training,
    TrainingQuestion,
    TrainingType,
    TrainingStatus,
    RequiredField,
)
from user.trainingreport import TrainingCertificateError, find_training_report_url
from user.userfiles import UserFiles
from user.validators import UsernameValidator, validate_name, validate_training_file_size
from user.validators import validate_institutional_email
from user.widgets import ProfilePhotoInput

from django.db.models import OuterRef, Exists

MIN_WORDS_RESEARCH_SUMMARY = settings.MIN_WORDS_RESEARCH_SUMMARY_CREDENTIALING


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
        'invalid_login': gettext_lazy(
            "Please enter a correct username/email and password. Note that the password "
            "field is case-sensitive."
        ),
        'inactive': gettext_lazy("This account has not been activated. Please check your "
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
        fields = ('password', 'is_active', 'is_admin')

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

                UserFiles().rename(self.old_file_root, self.instance)


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
            self.old_photo_path = UserFiles().get_photo_path(self.instance)

        return data

    def save(self):
        # Delete the old photo if the user is uploading a new photo, and
        # they already had one (before saving the new photo)
        if 'photo' in self.changed_data and hasattr(self, 'old_photo_path'):
            UserFiles().remove_photo(self.old_photo_path)
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

    if settings.PRIVACY_POLICY_HTML:
        privacy_policy = forms.BooleanField(required=True, label=mark_safe(settings.PRIVACY_POLICY_HTML))
    # Minimum and maximum number of seconds from when the client first
    # loads the page until the form may be submitted.
    MIN_SUBMISSION_SECONDS = 15
    MAX_SUBMISSION_SECONDS = 60 * 60

    # Rate limit for unactivated users (per IP address).
    MAX_UNACTIVATED_USERS = 20
    UNACTIVATED_USER_TIME_LIMIT = datetime.timedelta(hours=1)

    # Rate limit for activated+unactivated users (per IP address).
    MAX_NEW_USERS = 100
    NEW_USER_TIME_LIMIT = datetime.timedelta(hours=24)

    class Meta:
        model = User
        fields = ('email','username',)
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.current_time = int(time.time())

        if request is None:
            self.remote_addr = None
            self.form_load_time = None
        else:
            # Determine client's IP address.
            self.remote_addr = request.META['REMOTE_ADDR']

            # Determine the time when the form was initially loaded.
            # Set to zero (i.e., 1970-01-01) if the cookie is invalid.
            # The cookie becomes invalid if the client's IP address changes.
            cookie = request.get_signed_cookie('register_time', default='',
                                               salt=self.remote_addr)
            try:
                self.form_load_time = int(cookie)
            except ValueError:
                self.form_load_time = 0

    def clean(self):
        data = super().clean()
        if not self.errors and self.request is not None:
            elapsed_time = self.current_time - self.form_load_time
            if (elapsed_time < self.MIN_SUBMISSION_SECONDS
                    or elapsed_time > self.MAX_SUBMISSION_SECONDS):
                raise forms.ValidationError(
                    "Please wait a few seconds and try again."
                )

            old_users = User.objects.filter(registration_ip=self.remote_addr)

            if self.UNACTIVATED_USER_TIME_LIMIT:
                t = timezone.now() - self.UNACTIVATED_USER_TIME_LIMIT
                n = old_users.filter(join_date__gte=t, is_active=False).count()
                if n >= self.MAX_UNACTIVATED_USERS:
                    raise forms.ValidationError(
                        "You have tried to register too many accounts at once."
                    )

            if self.NEW_USER_TIME_LIMIT:
                t = timezone.now() - self.NEW_USER_TIME_LIMIT
                n = old_users.filter(join_date__gte=t).count()
                if n >= self.MAX_NEW_USERS:
                    raise forms.ValidationError(
                        "You have tried to register too many accounts at once."
                    )

        return data

    def set_response_cookies(self, response):
        # Update the register_time cookie if it is invalid or too old,
        # or if elapsed time is negative indicating a major clock
        # problem.  If the cookie is too new, leave it as-is.
        elapsed_time = self.current_time - self.form_load_time
        if elapsed_time < 0 or elapsed_time > self.MAX_SUBMISSION_SECONDS:
            response.set_signed_cookie('register_time', self.current_time,
                                       salt=self.remote_addr,
                                       secure=(not settings.DEBUG),
                                       httponly=True, samesite='Lax')

    def clean_username(self):
        "Record the original username in case it is needed"
        if User.objects.filter(username__iexact=self.cleaned_data['username']):
            raise forms.ValidationError("A user with that username already exists.")
        return self.cleaned_data['username'].lower()

    def save(self, sso_id=None):
        """
        Process the registration form
        """
        if self.errors:
            return

        user = super(RegistrationForm, self).save(commit=False)
        user.email = user.email.lower()
        user.sso_id = sso_id
        user.registration_ip = self.remote_addr

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
            'state_province': "The state or province where you live.",
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
            'state_province': 'State/Province (Required for Canada/U.S.)',
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
            'research_summary': f"""Please provide a detailed description of how you plan to use the data,
            including the name of any specific dataset(s) you intend to use. If you will be using the
            data for a class, please also include the name and number of the course.
            (Minimum : {MIN_WORDS_RESEARCH_SUMMARY} words)""",
        }
        widgets = {
           'research_summary': forms.Textarea(attrs={'rows': 2}),
        }

        labels = {
            'research_summary': 'Research Topic'
        }

    def clean_research_summary(self):
        research_summary = self.cleaned_data['research_summary']
        if len(research_summary.split()) < MIN_WORDS_RESEARCH_SUMMARY:
            raise forms.ValidationError("Please provide more information about your research topic.")
        return research_summary

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
            'reference_email': """The academic or institutional email address of your reference.""",
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
            if reference_email.lower() in [email.lower() for email in self.user.get_emails()]:
                raise forms.ValidationError("""You can not put yourself
                    as a reference.""")
            else:
                validate_institutional_email(reference_email)
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

        ref_required = True
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

        if (not self.instance and CredentialApplication.objects
                .filter(user=self.user, status=CredentialApplication.Status.PENDING)):
            raise forms.ValidationError('Outstanding application exists.')

    def save(self):
        credential_application = super().save(commit=False)
        slug = get_random_string(20)
        while CredentialApplication.objects.filter(slug=slug):
            slug = get_random_string(20)
        credential_application.reference_verification_token = get_random_string(32)
        credential_application.user = self.user
        credential_application.slug = slug
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

        # Deny (1) or approve (2)
        if self.cleaned_data['reference_response'] == 1:
            application.status = CredentialApplication.Status.REJECTED
        elif self.cleaned_data['reference_response'] == 2:
            application.update_review_status(40)

        application.reference_response_datetime = timezone.now()
        application.reference_response_text = self.cleaned_data['reference_response_text']
        application.save()
        return application


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


class TrainingForm(forms.ModelForm):
    completion_report = forms.FileField(widget=forms.HiddenInput(), disabled=True, required=False, label="Document",
                                        validators=[validate_training_file_size])
    completion_report_url = forms.URLField(widget=forms.HiddenInput(), disabled=True, required=False, label="URL")

    class Meta:
        model = Training
        fields = ('training_type', 'completion_report', 'completion_report_url')
        labels = {'training_type': 'Training Type'}

    def __init__(self, user, *args, **kwargs):
        self.user = user
        training_type_id = kwargs.pop('training_type', None)

        super().__init__(*args, **kwargs)

        self.training_type = TrainingType.objects.filter(id=training_type_id).first()

        self.fields['training_type'].initial = self.training_type

        if self.training_type is not None:
            self.fields['training_type'].help_text = self.training_type.description

            if self.training_type.required_field == RequiredField.DOCUMENT:
                self.fields['completion_report'].disabled = False
                self.fields['completion_report'].required = True
                self.fields['completion_report'].widget = forms.FileInput()
            elif self.training_type.required_field == RequiredField.URL:
                self.fields['completion_report_url'].disabled = False
                self.fields['completion_report_url'].required = True
                self.fields['completion_report_url'].widget = forms.URLInput()

    def clean(self):
        data = super().clean()

        trainings = Training.objects.filter(
            Q(status=TrainingStatus.REVIEW)
            | Q(status=TrainingStatus.ACCEPTED, training_type__valid_duration__isnull=True)
            | Q(
                status=TrainingStatus.ACCEPTED,
                process_datetime__gte=timezone.now() - F('training_type__valid_duration'),
            )
        ).filter(training_type=OuterRef('pk'), user=self.user)
        available_training_types = TrainingType.objects.annotate(training_exists=Exists(trainings)).filter(
            training_exists=False
        )

        if data['training_type'] not in available_training_types:
            raise forms.ValidationError('You have already submitted a training of this type.')

        # Check if the uploaded file is a PDF
        if data.get('completion_report') is not None:
            if not validate_pdf_file_type(data['completion_report']):
                raise forms.ValidationError('Invalid PDF file.')

        # Check for a recognized CITI verification link.
        # TODO: This is a hack and it should be replaced with something generalisable.
        if data['training_type'].name == 'CITI Data or Specimens Only Research':
            try:
                reportfile = data['completion_report']
                self.report_url = find_training_report_url(reportfile)
            except (TrainingCertificateError, KeyError):
                raise forms.ValidationError(
                    'Please upload the "Completion Report" file, '
                    'not the "Completion Certificate".')

    def save(self):
        training = super().save(commit=False)

        slug = get_random_string(20)
        while Training.objects.filter(slug=slug).exists():
            slug = get_random_string(20)

        training.slug = slug
        training.user = self.user
        training.save()

        training_questions = []
        for question in training.training_type.questions.all():
            training_questions.append(TrainingQuestion(training=training, question=question))

        TrainingQuestion.objects.bulk_create(training_questions)

        return training
