"""
API authentication with personal access tokens.

API views accept tokens only if they opt in by listing
PersonalAccessTokenAuthentication (and, for OAuth clients,
OAuth2Authentication) in authentication_classes, and they should pair
them with a TokenHasScopes permission so a token can only do what its
scopes allow.
"""

from oauth2_provider.models import AbstractAccessToken
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from user.models import PersonalAccessToken


class PersonalAccessTokenAuthentication(BaseAuthentication):
    """
    Authenticate requests sent with "Authorization: Bearer pnpat_...".

    Bearer tokens without the personal token prefix are left for other
    authentication classes (such as OAuth2Authentication) to handle.
    """

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if len(parts) != 2 or parts[0].lower() != b'bearer':
            return None
        try:
            token = parts[1].decode('ascii')
        except UnicodeDecodeError:
            return None
        if not token.startswith(PersonalAccessToken.PREFIX):
            return None

        record = PersonalAccessToken.authenticate(token)
        if record is None:
            raise AuthenticationFailed('Invalid or expired token.')
        return (record.user, record)

    def authenticate_header(self, request):
        return 'Bearer realm="api"'


class TokenHasScopes(BasePermission):
    """
    Allow a request only if its token grants the view's required scopes.

    Works with personal access tokens and OAuth access tokens. Requests
    authenticated any other way (for example with a session) are denied,
    so use this only on views meant to be called with a token.
    Subclasses can override get_scopes() to vary scopes by request.
    """

    def get_scopes(self, request, view):
        return getattr(view, 'required_scopes', None) or []

    def has_permission(self, request, view):
        scopes = self.get_scopes(request, view)
        if not scopes:
            return False
        token = request.auth
        if isinstance(token, PersonalAccessToken):
            return token.has_scopes(scopes)
        if isinstance(token, AbstractAccessToken):
            return token.is_valid(scopes)
        return False
