import json

from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from oauth2_provider.views.generic import ProtectedResourceView, ScopedProtectedResourceView
from oauth2_provider.oauth2_backends import get_oauthlib_core
from oauth2_provider.settings import oauth2_settings
from oauth2_provider.views import ConnectDiscoveryInfoView

import jwt
from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.views import View
from oauth2_provider.models import get_application_model
from cryptography.hazmat.primitives.serialization import load_pem_private_key

Application = get_application_model()


def _signing_key_pems():
    """Return active + rotated-out OIDC signing keys (PEM strings)."""
    keys = []
    if oauth2_settings.OIDC_RSA_PRIVATE_KEY:
        keys.append(oauth2_settings.OIDC_RSA_PRIVATE_KEY)
    keys.extend(getattr(oauth2_settings, 'OIDC_RSA_PRIVATE_KEYS_INACTIVE', []) or [])
    return keys


def _decode_id_token(id_token_hint):
    """Verify id_token_hint against any current signing key.

    exp is intentionally not enforced: a recently expired token is still a
    valid identity hint for "log this user out". verify_aud is False because
    PyJWT raises InvalidAudienceError otherwise when the JWT has an `aud`
    claim and no expected audience is passed; we read the aud claim
    downstream to look up the issuing Application, which then anchors the
    post_logout_redirect_uri allowlist check.
    """
    last_error = None
    for pem in _signing_key_pems():
        try:
            private_key = load_pem_private_key(pem.encode(), password=None)
            return jwt.decode(
                id_token_hint,
                private_key.public_key(),
                algorithms=["RS256"],
                options={"verify_signature": True, "verify_exp": False, "verify_aud": False},
            )
        except jwt.PyJWTError as e:
            last_error = e
    raise last_error or jwt.InvalidTokenError("no signing keys configured")


class EndSessionView(View):
    """OIDC RP-initiated logout (OpenID Connect Session Management 1.0)."""

    def get(self, request):
        return self._handle(request)

    def post(self, request):
        return self._handle(request)

    def _handle(self, request):
        id_token_hint = request.GET.get("id_token_hint") or request.POST.get("id_token_hint")
        post_logout = (
            request.GET.get("post_logout_redirect_uri")
            or request.POST.get("post_logout_redirect_uri", "")
        )

        application = None
        if id_token_hint:
            try:
                claims = _decode_id_token(id_token_hint)
                application = Application.objects.filter(client_id=claims.get("aud")).first()
            except jwt.PyJWTError:
                application = None

        # post_logout_redirect_uri honoured only if the issuing partner registered it
        if post_logout and application:
            partner = getattr(application, "partner", None)
            allowed = (partner.post_logout_redirect_uris.split() if partner else [])
            if post_logout not in allowed:
                post_logout = ""
        else:
            post_logout = ""

        logout(request)
        if post_logout:
            return redirect(post_logout)
        return render(request, "oauth/logged_out.html")


class PhysioNetDiscoveryView(ConnectDiscoveryInfoView):
    """
    Extends DOT's discovery view to publish endpoints DOT 2.2.0 omits from
    the response (introspection_endpoint).
    """

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        if response.status_code != 200:
            return response  # OIDC disabled / OIDCOnlyMixin returned 404
        data = json.loads(response.content)
        iss = oauth2_settings.OIDC_ISS_ENDPOINT.rstrip("/")
        data["introspection_endpoint"] = iss + reverse("oauth2_provider:introspect")
        data["end_session_endpoint"] = iss + reverse("oauth2_provider:end-session")
        new_response = JsonResponse(data)
        new_response["Access-Control-Allow-Origin"] = "*"
        return new_response


SCOPES_MAPPING = {
    "profile:read": lambda user: {
        "username": user.username,
        "full_name": user.get_full_name(),
    },
    "email:read": lambda user: {
        "email": user.get_primary_email().email if user.get_primary_email() else None,
    },
    "institution:read": lambda user: {
        "affiliation": user.profile.affiliation,
    },
    "credentialing:read": lambda user: {
        "credentialing_status": user.is_credentialed,
    },
    "orcid:read": lambda user: {
        "orcid": user.get_orcid_id(),
    },
    "public_id:read": lambda user: {
        "public_user_uuid": str(user.public_user_uuid),
    },
}


class UserInfoView(ScopedProtectedResourceView):
    """
    Returns selected user profile information based on the scopes associated
    with the provided OAuth2 token.

    Requires at minimum the "profile:read" scope.
    """
    required_scopes = ["profile:read"]

    def get(self, request, *args, **kwargs):

        valid, r = get_oauthlib_core().verify_request(request, scopes=self.required_scopes)
        if not valid:
            return JsonResponse({"error": "Invalid or missing token"}, status=403)

        token = r.access_token
        scopes = token.scope.split()
        user = token.user
        data = {}

        for scope, builder in SCOPES_MAPPING.items():
            if scope in scopes:
                data.update(builder(user))

        return JsonResponse(data)


class hello(ProtectedResourceView):
    def get(self, request, *args, **kwargs):
        return HttpResponse('Hello, OAuth2!')
