from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from oauth2_provider.models import AbstractApplication, get_device_grant_model
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauthlib.oauth2.rfc8628.grant_types import DeviceCodeGrant

from oauth.clients import DEVICE_FLOW_DEFAULT_SCOPES, DEVICE_FLOW_SCOPES, is_device_client
from user.models import AssociatedEmail

# Claims PhysioNet issues in ID tokens and at /oauth/oidc/userinfo. Kept in sync
# with the keys _build_claims() can produce; advertised via get_discovery_claims().
OIDC_SUPPORTED_CLAIMS = [
    "sub",
    "name",
    "given_name",
    "family_name",
    "preferred_username",
    "website",
    "email",
    "email_verified",
    "affiliation",
    "is_credentialed",
    "orcid",
    "public_user_uuid",
]


class CustomOAuth2Validator(OAuth2Validator):
    """
    Provide PhysioNet-specific OIDC claims for ID tokens and the UserInfo
    endpoint, keyed off the granted OAuth2 scopes.
    """

    # django-oauth-toolkit checks that the account is active only for the
    # password grant. These two checks make tokens stop working, and stop
    # being refreshed, as soon as an account is deactivated.

    def validate_bearer_token(self, token, scopes, request):
        """Reject access tokens whose owner's account is inactive."""
        if not super().validate_bearer_token(token, scopes, request):
            return False
        if not request.user.is_active:
            request.user = None
            request.access_token = None
            return False
        return True

    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs):
        """Reject refresh tokens whose owner's account is inactive."""
        if not super().validate_refresh_token(refresh_token, client, request, *args, **kwargs):
            return False
        return request.user.is_active

    # Device flow (RFC 8628). Device flow clients may only ask for a few
    # scopes, so a sign-in approved from a code cannot grant wide access.

    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
        if is_device_client(client) and not set(scopes) <= DEVICE_FLOW_SCOPES:
            return False
        return super().validate_scopes(client_id, scopes, client, request, *args, **kwargs)

    def get_default_scopes(self, client_id, request, *args, **kwargs):
        if is_device_client(request.client):
            return list(DEVICE_FLOW_DEFAULT_SCOPES)
        return super().get_default_scopes(client_id, request, *args, **kwargs)

    def validate_device_code(self, client_id, code, request, *args, **kwargs):
        """
        Report the status of a device code when the client polls for a token.

        A code can be exchanged for a token once, after the user approves
        it and before it expires, and only by the client it was issued to.
        Clients that poll faster than the agreed interval are told to slow
        down.
        """
        DeviceGrant = get_device_grant_model()
        grant = (
            DeviceGrant.objects.select_related("user")
            .filter(client_id=client_id, device_code=code)
            .first()
        )
        if grant is None:
            return None
        if grant.is_expired():
            return DeviceCodeGrant.DEVICE_CODE_EXPIRED
        if grant.status == DeviceGrant.DENIED:
            return DeviceCodeGrant.DEVICE_CODE_DENIED
        if grant.status == DeviceGrant.AUTHORIZATION_PENDING:
            now = timezone.now()
            # Allow a second of slack for network delays.
            too_soon = grant.last_checked > now - timedelta(seconds=grant.interval - 1)
            DeviceGrant.objects.filter(pk=grant.pk).update(last_checked=now)
            if too_soon:
                return DeviceCodeGrant.DEVICE_CODE_SLOW_DOWN
            return DeviceCodeGrant.DEVICE_CODE_PENDING
        if grant.status != DeviceGrant.AUTHORIZED or grant.user is None or not grant.user.is_active:
            return None

        # Use the code up, so it cannot be exchanged again. The status
        # check makes this safe if two requests arrive at once.
        used = DeviceGrant.objects.filter(pk=grant.pk, status=DeviceGrant.AUTHORIZED).update(
            status=DeviceGrant.EXPIRED
        )
        if not used:
            return None
        request.user = grant.user
        request.scopes = grant.scope.split()
        return DeviceCodeGrant.DEVICE_CODE_AUTHORIZED

    def _get_sub(self, user):
        return str(user.public_user_uuid)

    def _build_claims(self, user, scopes):
        claims = {"sub": self._get_sub(user)}

        if "profile" in scopes or "profile:read" in scopes:
            profile = getattr(user, 'profile', None)
            if profile:
                claims["name"] = user.get_full_name()
                claims["given_name"] = profile.first_names
                claims["family_name"] = profile.last_name
                claims["preferred_username"] = user.username
                if profile.website:
                    claims["website"] = profile.website

        if "email" in scopes or "email:read" in scopes:
            try:
                primary_email = user.get_primary_email()
            except AssociatedEmail.DoesNotExist:
                primary_email = None
            if primary_email:
                claims["email"] = primary_email.email
                claims["email_verified"] = primary_email.is_verified

        if "institution:read" in scopes:
            profile = getattr(user, 'profile', None)
            if profile:
                claims["affiliation"] = profile.affiliation

        if "credentialing:read" in scopes:
            claims["is_credentialed"] = user.is_credentialed

        if "orcid:read" in scopes:
            claims["orcid"] = user.get_orcid_id()

        if "public_id:read" in scopes:
            claims["public_user_uuid"] = str(user.public_user_uuid)

        return claims

    def get_additional_claims(self, request):
        if not (hasattr(request, 'user') and request.user):
            return {}
        scopes = set(getattr(request, 'scopes', []) or [])
        return self._build_claims(request.user, scopes)

    def get_oidc_claims(self, token, token_handler, request):
        """
        Bypass DOT's default oidc_claim_scope filter for ID token claims.
        DOT builds the ID token from get_oidc_claims(), which drops any claim
        whose name isn't in its built-in oidc_claim_scope map, so PhysioNet
        claims (affiliation, is_credentialed, orcid, public_user_uuid) never
        reach the ID token. _build_claims() already restricts each claim to
        its granted scope, so we can return it directly.
        """
        if not (hasattr(request, 'user') and request.user):
            return super().get_oidc_claims(token, token_handler, request)
        scopes = set(getattr(request, 'scopes', []) or [])
        return self._build_claims(request.user, scopes)

    def get_userinfo_claims(self, request):
        """
        Bypass DOT's default oidc_claim_scope filter so PhysioNet-specific
        scopes (institution:read, credentialing:read, orcid:read,
        public_id:read, profile:read, email:read) propagate through; DOT's
        filter only knows about its built-in OIDC standard claims.
        """
        if not (hasattr(request, 'user') and request.user):
            return super().get_userinfo_claims(request)
        scopes = set(getattr(request, 'scopes', []) or [])
        return self._build_claims(request.user, scopes)

    def get_discovery_claims(self, request):
        """
        Advertise the claims PhysioNet actually issues. DOT's default returns
        only ["sub"] here because our get_additional_claims() takes a request
        (so it isn't treated as request-agnostic), which understates what ID
        tokens and /oauth/oidc/userinfo return.
        """
        return list(OIDC_SUPPORTED_CLAIMS)

    def finalize_id_token(self, id_token, token, token_handler, request):
        """
        Fail with an actionable message when an application requests the
        'openid' scope without RS256 configured. Otherwise DOT reaches
        Application.jwk_key and raises the opaque "This application does not
        support signed tokens".
        """
        if request.client.algorithm != AbstractApplication.RS256_ALGORITHM:
            raise ImproperlyConfigured(
                f"OAuth application {request.client.name!r} requested the "
                "'openid' scope but is not configured for signed tokens. Set "
                "the application algorithm to RS256 for OIDC."
            )
        return super().finalize_id_token(id_token, token, token_handler, request)
