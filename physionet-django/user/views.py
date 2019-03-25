from datetime import datetime
import logging
import os
import pdb
import pytz

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.forms import inlineformset_factory, HiddenInput, CheckboxInput
from django.http import HttpResponse, Http404
from django.shortcuts import redirect, render
from django.template import loader
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .forms import AddEmailForm, AssociatedEmailChoiceForm, ProfileForm, RegistrationForm, UsernameChangeForm, CredentialApplicationForm, CredentialReferenceForm
from . import forms
from .models import AssociatedEmail, Profile, User, CredentialApplication, LegacyCredential
from physionet import utility
from project.models import Author, License
from notification.utility import reference_deny_credential, credential_application_request


logger = logging.getLogger(__name__)

def activate_user(request, uidb64, token):
    """
    Page to active the account of a newly registered user.
    """
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and not user.is_active and default_token_generator.check_token(user, token):
        user.is_active = True
        # Check legacy credentials
        check_legacy_credentials(user, user.email)
        user.save()
        email = user.associated_emails.first()
        email.verification_date = timezone.now()
        email.is_verified = True
        email.save()
        logger.info('User activated - {0}'.format(user.email))
        context = {'title':'Activation Successful', 'isvalid':True}
    else:
        logger.warning('Invalid Activation Link')
        context = {'title':'Invalid Activation Link', 'isvalid':False}

    return render(request, 'user/activate_user.html', context)


def check_legacy_credentials(user, email):
    """
    Check whether a user has already beeen credentialed on the old pn
    site. If so, credential their account and mark the migration.
    """
    legacy_credential = LegacyCredential.objects.filter(email=email,
        migrated=False)
    if legacy_credential:
        legacy_credential = legacy_credential.get()
        user.is_credentialed = True
        # All of them are mimic credentialed
        month, day, year = legacy_credential.mimic_approval_date.split('/')
        dt =  datetime(int(year), int(month), int(day))
        dt = pytz.timezone(timezone.get_default_timezone_name()).localize(dt)
        user.credential_datetime = dt
        legacy_credential.migrated = True
        legacy_credential.migration_date = timezone.now()
        legacy_credential.migrated_user = user
        legacy_credential.save()
        user.save()

def remove_email(request, email_id):
    "Remove a non-primary email associated with a user"
    user = request.user
    associated_email = AssociatedEmail.objects.get(id=email_id)
    if associated_email.user == user and not associated_email.is_primary_email:
        email = associated_email.email
        associated_email.delete()
        logger.info('Removed email {0} from user {1}'.format(email, user.id))
        messages.success(request, 'Your email: {0} has been removed from your account.'.format(email))

def set_primary_email(request, primary_email_form):
    "Set the selected email as the primary email"
    user = request.user
    if primary_email_form.is_valid():
        associated_email = primary_email_form.cleaned_data['associated_email']
        # Only do something if they selected a different email
        if associated_email.email != user.email:
            logger.info('Primary email changed from: {0} to {1}'.format(user.email, associated_email.email))
            user.email = associated_email.email
            user.save(update_fields=['email'])
            # Change the email field of author objects belonging to
            # the user. Warn them if they are the corresponding
            # author of any projects
            authors = Author.objects.filter(user=user)
            authors.update(corresponding_email=associated_email)
            messages.success(request, 'Your email: {0} has been set as your new primary email.'.format(user.email))
            if authors.filter(is_corresponding=True):
                messages.info(request, 'The corresponding email in all your authoring projects has been set to your new primary email.')


def set_public_email(request, public_email_form):
    "Set the selected email as the public email"
    user = request.user
    if public_email_form.is_valid():
        associated_email = public_email_form.cleaned_data['associated_email']
        current_public_email = user.associated_emails.filter(is_public=True).first()
        # Only do something if they selected a different email
        if associated_email != current_public_email:
            if current_public_email:
                current_public_email.is_public = False
                current_public_email.save()
            # The selection may be None
            if associated_email:
                associated_email.is_public = True
                associated_email.save()
                messages.success(request, 'Your email: {0} has been set to public.'.format(associated_email.email))
            else:
                messages.success(request, 'Your email: {0} has been set to private.'.format(current_public_email.email))

def add_email(request, add_email_form):
    user = request.user
    if add_email_form.is_valid():
        associated_email = AssociatedEmail.objects.create(user=user,
            email=add_email_form.cleaned_data['email'])
        # Send an email to the newly added email with a verification link
        uidb64 = force_text(urlsafe_base64_encode(force_bytes(associated_email.pk)))
        token = default_token_generator.make_token(user)
        subject = "PhysioNet Email Verification"
        context = {'name':user.get_full_name(),
            'domain':get_current_site(request), 'uidb64':uidb64, 'token':token}
        body = loader.render_to_string('user/email/verify_email_email.html', context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
            [add_email_form.cleaned_data['email']], fail_silently=False)
        messages.success(request, 'A verification link has been sent to: {0}'.format(associated_email.email))

@login_required
def edit_emails(request):
    """
    Edit emails page
    """
    user = request.user

    associated_emails = AssociatedEmail.objects.filter(
        user=user).order_by('-is_verified', '-is_primary_email')
    primary_email_form = AssociatedEmailChoiceForm(user=user,
                                                   selection_type='primary')
    public_email_form = AssociatedEmailChoiceForm(user=user,
                                                  selection_type='public')
    add_email_form = AddEmailForm()

    if request.method == 'POST':
        if 'remove_email' in request.POST:
            # No form. Just get button value.
            email_id = int(request.POST['remove_email'])
            remove_email(request, email_id)
        elif 'set_primary_email' in request.POST:
            primary_email_form = AssociatedEmailChoiceForm(user=user,
                selection_type='primary', data=request.POST)
            set_primary_email(request, primary_email_form)
        elif 'set_public_email' in request.POST:
            public_email_form = AssociatedEmailChoiceForm(user=user,
                selection_type='public', data=request.POST)
            set_public_email(request, public_email_form)

        elif 'add_email' in request.POST:
            add_email_form = AddEmailForm(request.POST)
            add_email(request, add_email_form)

    context = {'associated_emails':associated_emails,
        'primary_email_form':primary_email_form,
        'add_email_form':add_email_form,
        'public_email_form':public_email_form}

    context['messages'] = messages.get_messages(request)

    return render(request, 'user/edit_emails.html', context)


@login_required
def edit_profile(request):
    """
    Edit the profile fields
    """
    profile = request.user.profile
    form = ProfileForm(instance=profile)

    if request.method == 'POST':
        if 'edit_profile' in request.POST:
            # Update the profile and return to the same page. Place a message
            # at the top of the page: 'your profile has been updated'
            form = ProfileForm(data=request.POST, files=request.FILES,
                               instance=profile)
            if form.is_valid():
                form.save()
                messages.success(request, 'Your profile has been updated.')
        elif 'delete_photo' in request.POST:
            profile.delete_photo()
            messages.success(request, 'Your profile photo has been deleted.')

        if not form.errors:
            form = ProfileForm(instance=profile)

    return render(request, 'user/edit_profile.html', {'form':form})


@login_required
def edit_password_complete(request):
    """
    After password has successfully been changed. Need this view because
    we can't control the edit password view to show a success message.
    """
    return render(request, 'user/edit_password_complete.html')


def public_profile(request, username):
    """
    A user's public profile
    """
    if User.objects.filter(username=username).exists():
        public_user = User.objects.get(username=username)
        public_email = public_user.associated_emails.filter(is_public=True).first()
    else:
        raise Http404()

    return render(request, 'user/public_profile.html', {
        'public_user':public_user, 'profile':public_user.profile,
        'public_email':public_email})


def profile_photo(request, username):
    """
    Serve a user's profile photo
    """
    user = User.objects.get(username=username)
    return utility.serve_file(user.profile.photo.path)

def register(request):
    """
    User registration page
    """
    user = request.user
    if user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            # Create the new user
            user = form.save()

            # Send an email with the activation link
            uidb64 = force_text(urlsafe_base64_encode(force_bytes(user.pk)))
            token = default_token_generator.make_token(user)
            subject = "PhysioNet Account Activation"
            context = {'name':user.get_full_name(),
                'domain':get_current_site(request), 'uidb64':uidb64, 'token':token}
            body = loader.render_to_string('user/email/register_email.html', context)
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                [form.cleaned_data['email']], fail_silently=False)

            # Registration successful
            return render(request, 'user/register_done.html', {'email':user.email})
    else:
        form = RegistrationForm()

    return render(request, 'user/register.html', {'form':form})


@login_required
def user_settings(request):
    """
    Settings. Redirect to default - settings/profile
    Don't call this 'settings' because there's an import called 'settings'
    """
    return redirect('edit_profile')


def verify_email(request, uidb64, token):
    """
    Page to verify an associated email
    """
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        associated_email = AssociatedEmail.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, AssociatedEmail.DoesNotExist):
        associated_email = None

    if associated_email is not None:
        # Test the token with the user
        user = associated_email.user
        if default_token_generator.check_token(user, token):
            associated_email.verification_date = timezone.now()
            associated_email.is_verified = True
            associated_email.save()
            if not user.is_credentialed:
                check_legacy_credentials(user, associated_email.email)
            logger.info('User {0} verified another email {1}'.format(user.id, associated_email))
            return render(request, 'user/verify_email.html',
                {'title':'Verification Successful', 'isvalid':True})

    logger.warning('Invalid Verification Link')
    return render(request, 'user/verify_email.html',
        {'title':'Invalid Verification Link', 'isvalid':False})


@login_required
def edit_username(request):
    """
    Edit username settings page
    """
    user = request.user

    form = UsernameChangeForm(instance=user)
    if request.method == 'POST':
        form = UsernameChangeForm(instance=user, data=request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, 'Your username has been updated.')
        else:
            user = User.objects.get(id=user.id)

    return render(request, 'user/edit_username.html', {'form':form,
        'user':user})


@login_required
def edit_credentialing(request):
    """
    Credentials settings page.

    """
    applications = CredentialApplication.objects.filter(user=request.user)
    current_application = applications.filter(status=0).first()

    return render(request, 'user/edit_credentialing.html', {
        'applications':applications,
        'current_application':current_application})


@login_required
def user_credential_applications(request):
    """
    All the credential applications made by a user
    """
    applications = CredentialApplication.objects.filter(
        user=request.user).order_by('-application_datetime')

    return render(request, 'user/user_credential_applications.html',
        {'applications':applications})


@login_required
def credential_application(request):
    """
    Page to apply for credentially
    """
    user = request.user
    license = License.objects.get(id='6')
    if user.is_credentialed or CredentialApplication.objects.filter(
            user=user, status=0):
        return redirect('edit_credentialing')

    if request.method == 'POST':
        # We use the individual forms to render the errors in the template
        # if not all valid
        personal_form = forms.PersonalCAF(user=user, data=request.POST)
        training_form = forms.TrainingCAF(data=request.POST,
            files=request.FILES)
        reference_form = forms.ReferenceCAF(data=request.POST)
        course_form = forms.CourseCAF(data=request.POST, require_courses=False)

        form = CredentialApplicationForm(user=user, data=request.POST,
            files=request.FILES)

        if (personal_form.is_valid() and training_form.is_valid()
                and reference_form.is_valid() and course_form.is_valid()
                and form.is_valid()):
            aplication = form.save()
            credential_application_request(request, aplication)

            return render(request, 'user/credential_application_complete.html')
        else:
            messages.error(request, 'Invalid submission. See errors below.')
    else:
        personal_form = forms.PersonalCAF(user=user)
        training_form = forms.TrainingCAF()
        reference_form = forms.ReferenceCAF()
        course_form = forms.CourseCAF()
        form = None

    return render(request, 'user/credential_application.html', {'form':form,
        'personal_form':personal_form, 'training_form':training_form,
        'reference_form':reference_form, 'course_form':course_form,
        'license':license})


@login_required
def training_report(request, application_slug):
    """
    Serve a training report file
    """
    application = CredentialApplication.objects.get(slug=application_slug)
    if request.user == application.user or request.user.is_admin:
        return utility.serve_file(request, application.training_completion_report.path)


# @login_required
def credential_reference(request, application_slug):
    """
    Page for a reference to verify or reject a credential application
    """
    # application = CredentialApplication.objects.filter(
    #     slug=application_slug, reference_contact_datetime__isnull=False,
    #     reference_response_datetime=None)
    application = CredentialApplication.objects.filter(
        slug=application_slug, reference_response_datetime=None)
    
    if not application:
        return redirect('/')
    application = application.get()
    form = CredentialReferenceForm(instance=application)

    if request.method == 'POST':
        form = CredentialReferenceForm(data=request.POST, instance=application)
        if form.is_valid():
            application = form.save()
            # Automated email notifying that their reference has denied
            # their application.
            if application.reference_response == 1:
                reference_deny_credential(request, application)

            response = 'verifying' if application.reference_response == 2 else 'denying'
            return render(request, 'user/credential_reference_complete.html',
                {'response':response, 'application':application})
        else:
            messages.error(request, 'Invalid submission. See errors below.')

    return render(request, 'user/credential_reference.html',
        {'form':form, 'application':application})
