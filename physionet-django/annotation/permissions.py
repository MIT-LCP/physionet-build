from rest_framework.permissions import SAFE_METHODS

from user.token_auth import TokenHasScopes


class AnnotationsScope(TokenHasScopes):
    """
    Require the token scope for the view's resource: the read scope for
    safe methods and the write scope otherwise, e.g.
    "annotations:collections:write". These are the scopes listed in
    OAUTH2_PROVIDER["SCOPES"] and offered on the token settings page.
    """

    def get_scopes(self, request, view):
        access = "read" if request.method in SAFE_METHODS else "write"
        return ["annotations:{}:{}".format(view.scope_resource, access)]
