from datetime import datetime
import logging
import os
import pdb
import pytz

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
import django.contrib.auth.views as auth_views
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import IntegrityError
from django.forms import inlineformset_factory, HiddenInput, CheckboxInput
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.template import loader
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from django.db import transaction
from django.core.exceptions import ValidationError
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError

from user import forms, validators
from user.models import AssociatedEmail, Profile, Orcid, User, CredentialApplication, LegacyCredential, CloudInformation
from physionet import utility
from physionet.middleware.maintenance import (allow_post_during_maintenance,
                                              disallow_during_maintenance,
                                              ServiceUnavailable)
from project.models import Author, License, PublishedProject, DUASignature
from notification.utility import (process_credential_complete,
                                  credential_application_request,
                                  get_url_prefix, notify_account_registration)

logger = logging.getLogger(__name__)


@method_decorator(allow_post_during_maintenance, 'dispatch')
class LoginView(auth_views.LoginView):
    template_name = 'user/login.html'
    authentication_form = forms.LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


# Request password reset
class PasswordResetView(auth_views.PasswordResetView):
    template_name = 'user/reset_password_request.html'
    success_url = reverse_lazy('reset_password_sent')
    email_template_name = 'user/email/reset_password_email.html'


# Page shown after reset email has been sent
class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'user/reset_password_sent.html'


# Prompt user to enter new password and carry out password reset (if
# url is valid)
@method_decorator(disallow_during_maintenance, 'dispatch')
class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'user/reset_password_confirm.html'
    success_url = reverse_lazy('reset_password_complete')


# Password reset successfully carried out
class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = 'user/reset_password_complete.html'


class PasswordChangeView(auth_views.PasswordChangeView):
    success_url = reverse_lazy('edit_password_complete')
    template_name = 'user/edit_password.html'


login = LoginView.as_view()
logout = LogoutView.as_view()
reset_password_request = PasswordResetView.as_view()
reset_password_sent = PasswordResetDoneView.as_view()
reset_password_confirm = PasswordResetConfirmView.as_view()
reset_password_complete = PasswordResetCompleteView.as_view()
edit_password = PasswordChangeView.as_view()


@sensitive_post_parameters('password1', 'password2')
@disallow_during_maintenance
def activate_user(request, uidb64, token):
    """
    Page to active the account of a newly registered user.

    The user will create the password at this stage and then logged in.
    """
    activation_session_token = '_activation_reset_token'
    activation_url_token = 'user-activation'
    title = "Account activation"
    context = {'title': 'Invalid Activation Link', 'isvalid': False}

    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and user.is_active:
        messages.success(request, 'The account is active.')
        return redirect('login')

    if request.method == 'GET':
        if token == activation_url_token:
            session_token = request.session.get(activation_session_token)
            if default_token_generator.check_token(user, session_token):
                # If the token is valid, display the password reset form.
                form = forms.ActivationForm(user=user)
                return render(request, 'user/activate_user.html', {
                    'form': form, 'title': title})
        else:
            if default_token_generator.check_token(user, token):
                # Store the token in the session and redirect to the
                # password reset form at a URL without the token. That
                # avoids the possibility of leaking the token in the
                # HTTP Referer header.
                request.session[activation_session_token] = token
                redirect_url = request.path.replace(token, activation_url_token)
                return HttpResponseRedirect(redirect_url)
    else:
        if token == activation_url_token:
            session_token = request.session.get(activation_session_token)
            form = forms.ActivationForm(user=user, data=request.POST)
            if form.is_valid() and default_token_generator.check_token(user, session_token):
                with transaction.atomic():
                    user.set_password(form.cleaned_data['password1'])
                    user.is_active = True
                    # Check legacy credentials
                    check_legacy_credentials(user, user.email)
                    user.save()
                    email = user.associated_emails.first()
                    email.verification_date = timezone.now()
                    email.is_verified = True
                    email.save()
                    request.session.pop(activation_session_token)
                    logger.info('User activated - {0}'.format(user.email))
                    messages.success(request, 'The account has been activated.')
                    login(request, user)
                    return redirect('project_home')
            return render(request, 'user/activate_user.html', {'form': form,
                'title': title})

    return render(request, 'user/activate_user_complete.html', context)


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
        token = get_random_string(20)
        associated_email = AssociatedEmail.objects.create(user=user,
            email=add_email_form.cleaned_data['email'],
            verification_token=token)

        # Send an email to the newly added email with a verification link
        uidb64 = force_text(urlsafe_base64_encode(force_bytes(associated_email.pk)))
        subject = "PhysioNet Email Verification"
        context = {
            'name': user.get_full_name(),
            'domain': get_current_site(request),
            'url_prefix': get_url_prefix(request),
            'uidb64': uidb64,
            'token': token
        }
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
    primary_email_form = forms.AssociatedEmailChoiceForm(user=user,
                                                   selection_type='primary')
    public_email_form = forms.AssociatedEmailChoiceForm(user=user,
                                                  selection_type='public')
    add_email_form = forms.AddEmailForm()

    if request.method == 'POST':
        if 'remove_email' in request.POST:
            # No form. Just get button value.
            email_id = int(request.POST['remove_email'])
            remove_email(request, email_id)
        elif 'set_primary_email' in request.POST:
            primary_email_form = forms.AssociatedEmailChoiceForm(user=user,
                selection_type='primary', data=request.POST)
            set_primary_email(request, primary_email_form)
        elif 'set_public_email' in request.POST:
            public_email_form = forms.AssociatedEmailChoiceForm(user=user,
                selection_type='public', data=request.POST)
            set_public_email(request, public_email_form)

        elif 'add_email' in request.POST:
            add_email_form = forms.AddEmailForm(request.POST)
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
    form = forms.ProfileForm(instance=profile)

    if request.method == 'POST':
        if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
            # Allow submitting the form, but do not allow the photo to
            # be modified.
            if 'delete_photo' in request.POST or request.FILES:
                raise ServiceUnavailable()

        if 'edit_profile' in request.POST:
            # Update the profile and return to the same page. Place a message
            # at the top of the page: 'your profile has been updated'
            form = forms.ProfileForm(data=request.POST, files=request.FILES,
                               instance=profile)
            if form.is_valid():
                form.save()
                messages.success(request, 'Your profile has been updated.')
        elif 'delete_photo' in request.POST:
            profile.delete_photo()
            messages.success(request, 'Your profile photo has been deleted.')

        if not form.errors:
            form = forms.ProfileForm(instance=profile)

    return render(request, 'user/edit_profile.html', {'form':form})

@login_required
def edit_orcid(request):
    """
    Send a user to orcid.org for authorization to link to their ORCID account, then redirect them to
    views/auth_orcid to save their iD and other token information.  Also provide the option to unlink their
    ORCID account from their account.
    """

    if request.method == 'POST':
        if 'request_orcid' in request.POST:
            client_id = settings.ORCID_CLIENT_ID
            redirect_uri = settings.ORCID_REDIRECT_URI
            scope = list(settings.ORCID_SCOPE.split(","))
            oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scope)
            authorization_url, state = oauth.authorization_url(settings.ORCID_AUTH_URL)

            return redirect(authorization_url)

        if 'remove_orcid' in request.POST:
            try:
                Orcid.objects.get(user=request.user).delete()
                orcid_html = None
            except ObjectDoesNotExist:
                messages.error(request, 'Object Does Not Exist Error: tried to unlink an object which does not exist.')
                orcid_html = None

    else:
        try:
            orcid_html = Orcid.objects.get(user=request.user)
        except ObjectDoesNotExist:
            orcid_html = None

    return render(request, 'user/edit_orcid.html', {'orcid': orcid_html})

@login_required
@disallow_during_maintenance
def auth_orcid(request):
    """
    Gets a users iD and token information from an ORCID redirect URI after their authorization. Saves the iD and other
    token information. The access_token / refresh_token can be used to make token exchanges for additional
    information in the users account.  Public information can be read without access to the member API at ORCID. Limited
    access information requires an institution account with ORCID for access to the member API. The member API can also
    be used to add new information to a users ORCID profile (ex: a PhysioNet dataset project).  See the .env file for
    an example of how to do token exchanges.
    """

    client_id = settings.ORCID_CLIENT_ID
    client_secret = settings.ORCID_CLIENT_SECRET
    redirect_uri = settings.ORCID_REDIRECT_URI
    scope = list(settings.ORCID_SCOPE.split(","))
    oauth = OAuth2Session(client_id, redirect_uri=redirect_uri,
                          scope=scope)
    params = request.GET.copy()
    code = params['code']

    try:
        token = oauth.fetch_token(settings.ORCID_TOKEN_URL, code=code,
                                  include_client_id=True, client_secret=client_secret)
        try:
            validators.validate_orcid_token(token['access_token'])
            token_valid = True
        except ValidationError:
            messages.error(request, 'Validation Error: ORCID token validation failed.')
            token_valid = False
    except InvalidGrantError:
        messages.error(request, 'Invalid Grant Error: authorization code may be expired or invalid.')
        token_valid = False

    if token_valid:
        orcid_profile, _ = Orcid.objects.get_or_create(user=request.user)
        orcid_profile.orcid_id = token.get('orcid')
        orcid_profile.name = token.get('name')
        orcid_profile.access_token = token.get('access_token')
        orcid_profile.refresh_token = token.get('refresh_token')
        orcid_profile.token_type = token.get('token_type')
        orcid_profile.token_scope = token.get('scope')
        orcid_profile.token_expiration = token.get('expires_at')
        orcid_profile.full_clean()
        orcid_profile.save()

    return redirect('edit_orcid')

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
    if User.objects.filter(username__iexact=username, is_active=True).exists():
        public_user = User.objects.get(username__iexact=username)
        public_email = public_user.associated_emails.filter(is_public=True).first()
    else:
        raise Http404()

    # get list of projects
    projects = PublishedProject.objects.filter(authors__user=public_user).order_by('-publish_datetime')


    return render(request, 'user/public_profile.html', {
        'public_user':public_user, 'profile':public_user.profile,
        'public_email':public_email, 'projects':projects})


def profile_photo(_request, username):
    """
    Serve a user's profile photo
    """
    try:
        user = User.objects.get(username__iexact=username)
        if settings.STORAGE_TYPE == 'S3':
            return redirect(user.profile.photo.url)
        return utility.serve_file(user.profile.photo.path)
    except ObjectDoesNotExist:
        raise Http404()


def register(request):
    """
    User registration page
    """
    user = request.user
    if user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = forms.RegistrationForm(request.POST)
        if form.is_valid():
            # Create the new user
            try:
                user = form.save()
            except IntegrityError:
                form.full_clean()
                if form.is_valid():
                    raise
                user = User.objects.get(username=form.data['username'])
            else:
                uidb64 = force_text(urlsafe_base64_encode(force_bytes(
                    user.pk)))
                token = default_token_generator.make_token(user)
                notify_account_registration(request, user, uidb64, token)

            return render(request, 'user/register_done.html', {
                'email': user.email})
    else:
        form = forms.RegistrationForm()

    return render(request, 'user/register.html', {'form': form})


@login_required
def user_settings(request):
    """
    Settings. Redirect to default - settings/profile
    Don't call this 'settings' because there's an import called 'settings'
    """
    return redirect('edit_profile')


@login_required
@disallow_during_maintenance
def verify_email(request, uidb64, token):
    """
    Page to verify an associated email
    """
    user = request.user
    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        associated_email = AssociatedEmail.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, AssociatedEmail.DoesNotExist):
        associated_email = None

    if associated_email is not None and associated_email.user == user:
        # Test that the token is correct
        if associated_email.check_token(token):
            associated_email.verification_date = timezone.now()
            associated_email.is_verified = True
            associated_email.save()
            if not user.is_credentialed:
                check_legacy_credentials(user, associated_email.email)
            logger.info('User {0} verified another email {1}'.format(user.id, associated_email))
            messages.success(request, 'The email address {} has been verified.'.format(
                associated_email))
            return redirect('edit_emails')

    logger.warning('Invalid Verification Link')
    return render(request, 'user/verify_email.html',
        {'title':'Invalid Verification Link', 'isvalid':False})


@login_required
def edit_username(request):
    """
    Edit username settings page
    """
    user = request.user

    form = forms.UsernameChangeForm(instance=user)
    if request.method == 'POST':
        form = forms.UsernameChangeForm(instance=user, data=request.POST)

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
    if settings.PAUSE_CREDENTIALING:
        pause_applications = True
        pause_message = settings.PAUSE_CREDENTIALING_MESSAGE or (
            "We are not currently accepting new applications "
            "for credentialed access."
        )
    else:
        pause_applications = False
        pause_message = None

    applications = CredentialApplication.objects.filter(user=request.user)
    current_application = applications.filter(status=0).first()

    if request.method == 'POST' and 'withdraw_credentialing' in request.POST:
        if current_application:
            current_application.withdraw(responder=request.user)
            return render(request, 'user/withdraw_credentialing_success.html')
        else:
            messages.error(request, 'The application has already been processed.')

    return render(request, 'user/edit_credentialing.html', {
        'applications': applications,
        'pause_applications': pause_applications,
        'pause_message': pause_message,
        'current_application': current_application})


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

    if settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
        raise ServiceUnavailable()

    if request.method == 'POST':
        # We use the individual forms to render the errors in the template
        # if not all valid
        personal_form = forms.PersonalCAF(user=user, data=request.POST, prefix="application")
        training_form = forms.TrainingCAF(data=request.POST,
            files=request.FILES, prefix="application")
        research_form = forms.ResearchCAF(data=request.POST, prefix="application")
        reference_form = forms.ReferenceCAF(data=request.POST, prefix="application", user=user)

        form = forms.CredentialApplicationForm(user=user, data=request.POST,
            files=request.FILES,  prefix="application")

        if (personal_form.is_valid() and training_form.is_valid()
                and reference_form.is_valid()
                and form.is_valid()) and research_form.is_valid():
            application = form.save()
            credential_application_request(request, application)

            return render(request, 'user/credential_application_complete.html')
        else:
            messages.error(request, 'Invalid submission. See errors below.')
    else:
        personal_form = forms.PersonalCAF(user=user, prefix="application")
        training_form = forms.TrainingCAF(prefix="application")
        reference_form = forms.ReferenceCAF(prefix="application", user=user)
        research_form = forms.ResearchCAF(prefix="application")
        form = None

    return render(request, 'user/credential_application.html', {'form':form,
        'personal_form':personal_form, 'training_form':training_form,
        'reference_form':reference_form, 'license':license, 
        'research_form':research_form})


@login_required
def training_report(request, application_slug, attach=True):
    """
    Serve a training report file
    """
    try:
        application = CredentialApplication.objects.get(slug=application_slug)
    except ObjectDoesNotExist:
        raise Http404()

    if request.user == application.user or request.user.is_admin:
        try:
            return utility.serve_file(application.training_completion_report.path,
                                      attach=attach)
        except FileNotFoundError:
            raise Http404()

    raise PermissionDenied()


@login_required
def training_report_view(request, application_slug):
    """
    Wrapper for training_report. Serves the training report in the browser
    for KP's custom pages.
    """
    return training_report(request, application_slug, attach=False)


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
    form = forms.CredentialReferenceForm(instance=application)

    if request.method == 'POST':
        form = forms.CredentialReferenceForm(data=request.POST, instance=application)
        if form.is_valid():
            application = form.save()
            # Automated email notifying that their reference has denied
            # their application.
            if application.reference_response == 1:
                process_credential_complete(request, application,
                                            comments=False)

            response = 'verifying' if application.reference_response == 2 else 'denying'
            return render(request, 'user/credential_reference_complete.html',
                {'response': response, 'application': application})
        else:
            messages.error(request, 'Invalid submission. See errors below.')

    return render(request, 'user/credential_reference.html',
        {'form': form, 'application': application})

@login_required
def edit_cloud(request):
    """
    Page to add the information for cloud usage. 
    """
    user = request.user
    cloud_info = CloudInformation.objects.get_or_create(user=user)[0]
    form = forms.CloudForm(instance=cloud_info)
    if request.method == 'POST':
        form = forms.CloudForm(instance=cloud_info, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your cloud information has been saved.')
        else:
            messages.error(request, 'Invalid submission. See errors below.')

    return render(request, 'user/edit_cloud.html', {'form':form, 'user':user})

@login_required
def view_agreements(request):
    """
    View a list of signed agreements in the user profile.
    """
    user = request.user
    signed = DUASignature.objects.filter(user=user).order_by('-sign_datetime')

    return render(request, 'user/view_agreements.html', {'user': user,
                                                         'signed': signed})

@login_required
def view_signed_agreement(request, id):
    """
    View a printable agreement in the user profile.
    """
    user = request.user
    signed = DUASignature.objects.get(user=user, id=id)

    return render(request, 'user/view_signed_agreement.html',
                  {'user': user, 'signed': signed})
