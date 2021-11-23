import logging

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.encoding import force_bytes, force_text
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from notification.utility import notify_account_registration
from physionet.middleware.maintenance import disallow_during_maintenance
from sso import forms
from user.models import User

logger = logging.getLogger(__name__)


def sso_login(request):
    # If the given user exists => authenticate the user, redirect to desired page
    # If the given user does not exists => redirect to sso/register
    remote_sso_id = request.META.get('HTTP_REMOTE_USER')

    if request.user.is_authenticated:
        return redirect('home')

    user = authenticate(remote_user=remote_sso_id)
    if user is not None:
        auth_login(request, user)
    else:
        return redirect('sso_register')

    return redirect('home')


def sso_register(request):
    user = request.user
    if user.is_authenticated:
        return redirect('home')

    remote_sso_id = request.META.get('HTTP_REMOTE_USER')

    # REMOTE_USER should be set by Shibboleth (if it's not then it's a config issue)
    if not remote_sso_id:
        return redirect('login')

    if request.method == 'POST':
        form = forms.SSORegistrationForm(request.POST, sso_id=remote_sso_id)

        if form.is_valid():
            user = form.save()
            uidb64 = force_text(urlsafe_base64_encode(force_bytes(user.pk)))
            token = default_token_generator.make_token(user)
            notify_account_registration(request, user, uidb64, token, sso=True)
            return render(request, 'user/register_done.html', {'email': user.email, 'sso': True})
    else:
        try:
            remote_user = User.objects.get(sso_id=remote_sso_id)
            return render(request, 'user/register_done.html', {'email': remote_user.email, 'sso': True})
        except User.DoesNotExist:
            form = forms.SSORegistrationForm()

    return render(request, 'sso/register.html', {'form': form})


@disallow_during_maintenance
def sso_activate_user(request, uidb64, token):
    context = {'title': 'Invalid Activation Link', 'isvalid': False}

    try:
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and user.is_active:
        messages.success(request, 'The account is active.')
        return redirect('sso_login')

    if default_token_generator.check_token(user, token):
        with transaction.atomic():
            user.is_active = True
            user.save()
            email = user.associated_emails.first()
            email.verification_date = timezone.now()
            email.is_verified = True
            email.save()
            logger.info('User activated - {0}'.format(user.email))
            messages.success(request, 'The account has been activated.')

        auth_login(request, user, backend='sso.auth.RemoteUserBackend')
        return redirect('project_home')

    return render(request, 'user/activate_user_complete.html', context)
