from oauth2_provider.oauth2_validators import OAuth2Validator


class CustomOAuth2Validator(OAuth2Validator):
    """
    Custom validator that provides PhysioNet-specific OIDC claims
    via get_additional_claims (for ID tokens) and get_userinfo_claims
    (for the UserInfo endpoint).
    """

    def _get_sub(self, user):
        return str(user.public_user_uuid)

    def _build_claims(self, user, scopes):
        """Build claims dict filtered by the granted scopes."""
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
            except Exception:
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
        """Called by DOT when generating ID tokens."""
        if not request.user:
            return {}
        scopes = set(getattr(request, 'scopes', []) or [])
        return self._build_claims(request.user, scopes)

    def get_userinfo_claims(self, request):
        """Called by DOT for the OIDC UserInfo endpoint."""
        claims = super().get_userinfo_claims(request)
        if hasattr(request, 'user') and request.user:
            claims["sub"] = self._get_sub(request.user)
        return claims
