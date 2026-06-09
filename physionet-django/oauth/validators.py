from django.core.exceptions import ImproperlyConfigured
from oauth2_provider.models import AbstractApplication
from oauth2_provider.oauth2_validators import OAuth2Validator

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
