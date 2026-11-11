"""
Device flow (RFC 8628) views.

A script, such as the PhysioNet Python package, asks for a code at the
device authorization endpoint and shows the user a short user code. The
user enters it at /oauth/device/ while signed in, checks what is being
requested, and approves it. Meanwhile the script polls the token
endpoint, and gets a token once the user has approved.

These views wrap the ones in django-oauth-toolkit to:
- accept device codes only for applications registered for the device
  flow,
- return an absolute verification URI for the current site,
- accept user codes in any case, with or without the hyphen,
- rate limit failed code entries, and
- use PhysioNet's templates, which warn users to approve only sign-ins
  they started themselves.
"""

import hashlib
import json
from datetime import timedelta

from django import forms
from django.conf import settings
from django.core.cache import caches
from django.db.models import Q
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils import timezone
from oauth2_provider import views as oauth2_views
from oauth2_provider.models import get_application_model, get_device_grant_model
from oauth2_provider.views.device import DeviceGrantForm

from oauth.clients import is_device_client
from oauth.user_codes import format_user_code
from physionet.utility import get_client_ip


class DeviceAuthorizationView(oauth2_views.DeviceAuthorizationView):
    """
    Start a device sign-in, for applications registered for the device flow.

    This replaces DOT's post(), which fails with oauthlib 4 (the response
    now includes the resolved scope).
    """

    def post(self, request, *args, **kwargs):
        # Each successful request stores a code, so limit requests per address.
        key = "device-authorizations:client:{}".format(_client_hash(request))
        if (_cache().get(key) or 0) >= settings.DEVICE_AUTHORIZATION_CLIENT_LIMIT:
            return _no_store(JsonResponse(
                {
                    "error": "too_many_requests",
                    "error_description": "Too many sign-in requests. Please try again later.",
                },
                status=429,
            ))
        _count(key)

        client_id = request.POST.get("client_id", "")
        application = get_application_model().objects.filter(client_id=client_id).first()
        if application is not None and not is_device_client(application):
            return _no_store(JsonResponse(
                {
                    "error": "unauthorized_client",
                    "error_description": "This client is not allowed to use the device flow.",
                },
                status=400,
            ))

        headers, body, status = self.create_device_authorization_response(request)
        if status != 200:
            return JsonResponse(json.loads(body), status=status, headers=headers)

        # oauthlib returns the scopes it validated, including defaults.
        scope = body.pop("scope", "")
        get_device_grant_model().objects.create(
            client_id=client_id,
            device_code=body["device_code"],
            user_code=body["user_code"],
            scope=scope,
            interval=body.get("interval") or 5,
            expires=timezone.now() + timedelta(seconds=body["expires_in"]),
        )
        body["verification_uri"] = request.build_absolute_uri(reverse("oauth2_provider:device"))
        return _no_store(JsonResponse(body))


def _no_store(response):
    response["Cache-Control"] = "no-store"
    return response


def _cache():
    # The login failure cache is kept in the database, so counts are shared
    # by every server process.
    return caches["login_failures"]


def _client_hash(request):
    return hashlib.sha256((get_client_ip(request) or "").encode()).hexdigest()


def _count(key):
    """Add one to a counter that resets LOGIN_FAILURE_WINDOW seconds after it starts."""
    cache = _cache()
    if not cache.add(key, 1, settings.LOGIN_FAILURE_WINDOW):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, settings.LOGIN_FAILURE_WINDOW)


def _failure_keys(request):
    return (
        ("device-code-failures:user:{}".format(request.user.pk), settings.DEVICE_CODE_FAILURE_LIMIT),
        ("device-code-failures:client:{}".format(_client_hash(request)), settings.DEVICE_CODE_FAILURE_CLIENT_LIMIT),
    )


def _is_limited(request):
    return any((_cache().get(key) or 0) >= limit for key, limit in _failure_keys(request))


def _record_failure(request):
    for key, _ in _failure_keys(request):
        _count(key)


class UserCodeForm(DeviceGrantForm):
    user_code = forms.CharField(label="Code", max_length=20)

    def clean_user_code(self):
        self.cleaned_data["user_code"] = format_user_code(self.cleaned_data["user_code"])
        return super().clean_user_code()


class DeviceUserCodeView(oauth2_views.DeviceUserCodeView):
    """Page where a signed-in user enters the code shown by their script."""

    template_name = "oauth/device_code.html"
    form_class = UserCodeForm

    def post(self, request, *args, **kwargs):
        if _is_limited(request):
            context = self.get_context_data(form=self.form_class(), limited=True)
            return self.render_to_response(context, status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """
        Link the code to this user, unless another user has already
        entered it. The update is conditional so that two users entering
        the same code at once cannot both claim it.
        """
        grant = form.cleaned_data["device_grant"]
        DeviceGrant = get_device_grant_model()
        claimed = (
            DeviceGrant.objects.filter(pk=grant.pk, status=DeviceGrant.AUTHORIZATION_PENDING)
            .filter(Q(user__isnull=True) | Q(user=self.request.user))
            .update(user=self.request.user)
        )
        if not claimed:
            form.add_error("user_code", "User code has already been used")
            return self.form_invalid(form)
        self.device_grant = grant
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        _record_failure(self.request)
        return super().form_invalid(form)


class DeviceConfirmView(oauth2_views.DeviceConfirmView):
    """Page where the user approves or denies a device sign-in."""

    template_name = "oauth/device_confirm.html"

    def form_valid(self, form):
        """
        Approve or deny the code. The update only applies while the code is
        still pending, so a repeated or overlapping submission (such as a
        double click) cannot undo a later state, for example making a code
        that has already been exchanged usable again.
        """
        DeviceGrant = get_device_grant_model()
        statuses = {"accept": DeviceGrant.AUTHORIZED, "deny": DeviceGrant.DENIED}
        status = statuses.get(form.cleaned_data["action"])
        if status is None:
            return HttpResponseBadRequest()
        DeviceGrant.objects.filter(
            pk=self.get_object().pk, user=self.request.user, status=DeviceGrant.AUTHORIZATION_PENDING
        ).update(status=status)
        # The status page shows the code's current state.
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_code"] = self.kwargs["user_code"]
        return context


class DeviceGrantStatusView(oauth2_views.DeviceGrantStatusView):
    """Page shown after the user approves or denies a device sign-in."""

    template_name = "oauth/device_status.html"
