from oauth2_provider.models import get_application_model
from oauth2_provider.oauth2_validators import OAuth2Validator

from oauth.models import Partner
from user.models import AssociatedEmail

Application = get_application_model()


class CustomOAuth2Validator(OAuth2Validator):
    """
    Provide PhysioNet-specific OIDC claims for ID tokens and the UserInfo
    endpoint, keyed off the granted OAuth2 scopes.
    """

    def _get_sub(self, user):
        """Return the stable subject identifier for an OIDC token."""
        return str(user.public_user_uuid)

    def _build_claims(self, user, scopes):
        """Build the claim set for a user filtered by the granted scopes."""
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

    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
        """Enforce per-partner scope allowlist on top of DOT's global SCOPES check."""
        if not super().validate_scopes(client_id, scopes, client, request, *args, **kwargs):
            return False
        partner = getattr(client, 'partner', None)
        if partner is None:
            return True  # Application predates Partner model; legacy compat
        if not partner.allowed_scopes:
            return True  # empty list = wildcard, intentional for legacy
        return set(scopes).issubset(set(partner.allowed_scopes))

    def validate_client_id(self, client_id, request, *args, **kwargs):
        """Reject /authorize for suspended/revoked partners before the consent screen."""
        if not super().validate_client_id(client_id, request, *args, **kwargs):
            return False
        partner = getattr(request.client, 'partner', None)
        if partner and partner.status != Partner.Status.ACTIVE:
            return False
        return True

    def authenticate_client(self, request, *args, **kwargs):
        """Block client authentication for suspended/revoked partners at /token, /introspect, /revoke-token."""
        if not super().authenticate_client(request, *args, **kwargs):
            return False
        partner = getattr(request.client, 'partner', None)
        if partner and partner.status != Partner.Status.ACTIVE:
            return False
        return True

    def is_pkce_required(self, client_id, *args, **kwargs):
        """Allow per-partner PKCE opt-out.

        OAuth 2.1 / RFC 9700 require PKCE; the global PKCE_REQUIRED setting
        (default True) is honored first. When the global says "require",
        an individual partner with Partner.requires_pkce=False can still
        opt out — used when the upstream IdP can't send a code_challenge.
        When the global says "don't require" (typically dev/test), nobody
        requires it.
        """
        global_required = super().is_pkce_required(client_id, *args, **kwargs)
        if not global_required:
            return False
        try:
            app = Application.objects.get(client_id=client_id)
        except Application.DoesNotExist:
            return True
        partner = getattr(app, 'partner', None)
        if partner is None:
            return True
        return partner.requires_pkce

    def get_additional_claims(self, request):
        """Return the additional claims to embed in the ID token."""
        if not request.user:
            return {}
        scopes = set(getattr(request, 'scopes', []) or [])
        return self._build_claims(request.user, scopes)

    def get_userinfo_claims(self, request):
        """Return the claims served from the OIDC UserInfo endpoint.

        Bypasses DOT's default oidc_claim_scope filter so PhysioNet-specific
        scopes (institution:read, credentialing:read, orcid:read,
        public_id:read, profile:read, email:read) propagate through; DOT's
        filter only knows about its built-in OIDC standard claims.
        """
        if not (hasattr(request, 'user') and request.user):
            return super().get_userinfo_claims(request)
        scopes = set(getattr(request, 'scopes', []) or [])
        return self._build_claims(request.user, scopes)
