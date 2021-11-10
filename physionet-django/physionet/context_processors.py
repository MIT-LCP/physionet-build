from django.conf import settings

from project.models import AccessPolicy


def access_policy(request):
    return {'AccessPolicy': AccessPolicy}


def platform_name(request):
    return {'SITE_NAME': settings.SITE_NAME}
