"""
API authentication with personal access tokens.

API views accept tokens only if they opt in by listing
PersonalAccessTokenAuthentication (and, for OAuth clients,
OAuth2Authentication) in authentication_classes, and they should pair
them with a TokenHasScopes permission so a token can only do what its
scopes allow.
"""

from oauth2_provider.models import AbstractAccessToken
from oauth2_provider.oauth2_backends import get_oauthlib_core
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from oauth.clients import FIRST_PARTY_CLIENT_IDS
from user.models import PersonalAccessToken

# The scope that lets a third-party OAuth application read a user's
# credentialing and training status.
CREDENTIALING_READ_SCOPE = 'credentialing:read'


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


def _bearer_token(request):
    """The bearer token sent with a request, or None."""
    parts = get_authorization_header(request).split()
    if len(parts) != 2 or parts[0].lower() != b'bearer':
        return None
    try:
        return parts[1].decode('ascii')
    except UnicodeDecodeError:
        return None


class AccountStatusTokenAuthentication(BaseAuthentication):
    """
    Authenticate bearer tokens that may read the account's own access status.

    Accepted, as the token's user:
        - a personal access token, whatever its scopes: the user created it
          for themselves;
        - an OAuth token issued to one of PhysioNet's own applications
          (oauth.clients.FIRST_PARTY_CLIENT_IDS), such as the Python package;
        - any other OAuth token with the credentialing:read scope.

    A valid token that is none of these (for example a third-party token
    with only profile:read) is ignored, so the request is answered as
    anonymous: the user did not let that application read their
    credentialing or training status. An invalid or expired token is
    rejected with 401, as wrong Basic credentials are, so clients know to
    refresh it.
    """

    def authenticate(self, request):
        token = _bearer_token(request)
        if token is None:
            return None
        if token.startswith(PersonalAccessToken.PREFIX):
            record = PersonalAccessToken.authenticate(token)
            if record is None:
                raise AuthenticationFailed('Invalid or expired token.')
            return (record.user, record)

        valid, oauth_request = get_oauthlib_core().verify_request(request, scopes=[])
        if not valid:
            raise AuthenticationFailed('Invalid or expired token.')
        access_token = oauth_request.access_token
        if not access_token.user.is_active:
            raise AuthenticationFailed('Invalid or expired token.')
        application = access_token.application
        first_party = application is not None and application.client_id in FIRST_PARTY_CLIENT_IDS
        if first_party or access_token.allow_scopes([CREDENTIALING_READ_SCOPE]):
            return (access_token.user, access_token)
        return None

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
