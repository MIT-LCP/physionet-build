import logging

import django.contrib.auth.views as auth_views
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from notification.utility import notify_account_registration
from physionet.middleware.maintenance import disallow_during_maintenance
from sso import forms
from user.models import User

logger = logging.getLogger(__name__)


class SSOLogin(auth_views.LoginView):
    """SSO Login view

    This view should be protected by an appropriate Shibboleth proxy.
    SSO_REMOTE_USER_HEADER should be set by the proxy.

    If the user is able to access this view it means that they are authenticated using SSO.
    """

    http_method_names = ['get', 'head']

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.get_success_url())

        remote_sso_id = self.request.META.get(settings.SSO_REMOTE_USER_HEADER)

        # This should not happen as the SSO_REMOTE_USER_HEADER header should be always set by Nginx
        if remote_sso_id is None:
            return redirect('login')

        user = authenticate(remote_user=remote_sso_id)
        if user is not None:
            auth_login(request, user)
        else:
            # Remote user seen for the first time, redirect to SSO registration form
            return redirect('sso_register')

        return redirect(self.get_success_url())


sso_login = SSOLogin.as_view()


def sso_register(request):
    """SSO Registration view

    This view should be protected by an appropriate Shibboleth proxy.
    SSO_REMOTE_USER_HEADER should be set by the proxy.

    GET does two things:
      - if the user did not fill it renders the registration form.
      - if the user filled the form but didn't click the confirmation url it renders a message that tells
        the user to click this link.

    POST submits the registration form.
    """
    user = request.user
    if user.is_authenticated:
        return redirect('project_home')

    remote_sso_id = request.META.get(settings.SSO_REMOTE_USER_HEADER)

    # This should not happen as the SSO_REMOTE_USER_HEADER header should be always set by Nginx
    if not remote_sso_id:
        return redirect('login')

    if request.method == 'POST':
        form = forms.SSORegistrationForm(request.POST, sso_id=remote_sso_id)

        if form.is_valid():
            user = form.save()
            uidb64 = force_str(urlsafe_base64_encode(force_bytes(user.pk)))
            token = default_token_generator.make_token(user)
            notify_account_registration(request, user, uidb64, token, sso=True)
            return render(request, 'user/register_done.html', {'email': user.email, 'sso': True})
    else:
        try:
            remote_user = User.objects.get(sso_id=remote_sso_id)
            if remote_user.is_active:
                return redirect('sso_login')
            return render(request, 'user/register_done.html', {'email': remote_user.email, 'sso': True})
        except User.DoesNotExist:
            form = forms.SSORegistrationForm()

    return render(request, 'sso/register.html', {'form': form})


@disallow_during_maintenance
def sso_activate_user(request, uidb64, token):
    """SSO Registration view

    This view should be protected by an appropriate Shibboleth proxy.
    SSO_REMOTE_USER_HEADER should be set by the proxy.
    """
    context = {'title': 'Invalid Activation Link', 'isvalid': False}

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        remote_sso_id = request.META.get(settings.SSO_REMOTE_USER_HEADER)
        user = User.objects.get(pk=uid, sso_id=remote_sso_id)
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
