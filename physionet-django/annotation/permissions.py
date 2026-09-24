from oauth2_provider.contrib.rest_framework import TokenHasScope
from rest_framework.permissions import DjangoModelPermissions, SAFE_METHODS


class AnnotationsScope(TokenHasScope):
    def get_scopes(self, request, view):
        return (
            ["annotations:annotations:read"]
            if request.method in SAFE_METHODS
            else ["annotations:annotations:write"]
        )


class AnnotationsTypesScope(TokenHasScope):
    def get_scopes(self, request, view):
        return (
            ["annotations:types:read"]
            if request.method in SAFE_METHODS
            else ["annotations:types:write"]
        )


class AnnotationsCollectionsScope(TokenHasScope):
    def get_scopes(self, request, view):
        return (
            ["annotations:collections:read"]
            if request.method in SAFE_METHODS
            else ["annotations:collections:write"]
        )
