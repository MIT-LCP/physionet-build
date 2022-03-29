from django import template
from django.conf import settings

register = template.Library()


def sso_enabled(request):
    return {'sso_enabled': settings.ENABLE_SSO}
