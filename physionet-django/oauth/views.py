from django.http import HttpResponse, JsonResponse
from oauth2_provider.views.generic import ProtectedResourceView, ScopedProtectedResourceView
from oauth2_provider.oauth2_backends import get_oauthlib_core


class UserInfoView(ScopedProtectedResourceView):
    """
    Returns selected user profile information based on the scopes associated
    with the provided OAuth2 token.

    This view supports the following scopes:
    - 'profile:read': returns `username` and `full_name`
    - 'email:read': returns `email`
    - 'institution:read': returns `institution`
    - 'credentialing:read': returns `training_status` and `credentialing_status`
    - 'orcid:read': returns `orcid`
    - 'public_id:read': returns `public_user_uuid`

    Only fields corresponding to granted scopes are included in the response.
    """
    required_scopes = []

    def get(self, request, *args, **kwargs):

        valid, r = get_oauthlib_core().verify_request(request, scopes=[])
        if not valid:
            return JsonResponse({"error": "Invalid or missing token"}, status=403)

        token = r.access_token
        scopes = token.scope.split()

        user = token.user
        data = {}

        if "profile:read" in scopes:
            data["username"] = user.username
            data["full_name"] = user.profile.get_full_name()

        if "email:read" in scopes:
            data["email"] = user.email

        if "institution:read" in scopes:
            data["institution"] = user.institution

        if "credentialing:read" in scopes:
            data["training_status"] = user.training_status
            data["credentialing_status"] = user.credentialing_status

        if "orcid:read" in scopes:
            data["orcid"] = user.orcid

        if "public_id:read" in scopes:
            data["public_user_uuid"] = str(user.public_user_uuid)

        return JsonResponse(data)


class hello(ProtectedResourceView):
    def get(self, request, *args, **kwargs):
        return HttpResponse('Hello, OAuth2!')
