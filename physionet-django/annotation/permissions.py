from oauth2_provider.contrib.rest_framework import TokenHasScope
from rest_framework.permissions import DjangoModelPermissions, SAFE_METHODS


class AnnotationsScope(TokenHasScope):
    def get_scopes(self, request, view):
        return (
            ["annotations:view"]
            if request.method in SAFE_METHODS
            else ["annotations:edit"]
        )
