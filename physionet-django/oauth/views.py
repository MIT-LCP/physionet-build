from django.http import HttpResponse, JsonResponse
from oauth2_provider.views.generic import ProtectedResourceView, ScopedProtectedResourceView
from oauth2_provider.oauth2_backends import get_oauthlib_core


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
