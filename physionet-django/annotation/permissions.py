from oauth2_provider.contrib.rest_framework import TokenHasScope
from rest_framework.permissions import DjangoModelPermissions, SAFE_METHODS


class AnnotationsScope(TokenHasScope):
    def get_scopes(self, request, view):
        return (
            ["annotations:read"]
            if request.method in SAFE_METHODS
            else ["annotations:write"]
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

class DjangoModelPermissionsWithView(DjangoModelPermissions):
    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": ["%(app_label)s.view_%(model_name)s"],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }
