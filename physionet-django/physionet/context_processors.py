from django.conf import settings

from physionet.models import StaticPage
from project.models import AccessPolicy


def access_policy(request):
    return {'AccessPolicy': AccessPolicy}


def storage_type(request):
    return {'STORAGE_TYPE': settings.STORAGE_TYPE}


def platform_config(request):
    return {
        'SITE_NAME': settings.SITE_NAME,
        'FOOTER_MANAGED_BY': settings.FOOTER_MANAGED_BY,
        'FOOTER_SUPPORTED_BY': settings.FOOTER_SUPPORTED_BY,
        'FOOTER_ACCESSIBILITY_PAGE': settings.FOOTER_ACCESSIBILITY_PAGE,
        'STRAPLINE': settings.STRAPLINE,
        'SOURCE_CODE_REPOSITORY_LINK': settings.SOURCE_CODE_REPOSITORY_LINK
    }

def static_pages(_):
    """ Retrieves static page for the templates """

    static_page_obj = StaticPage.objects.all().order_by('nav_order')
    return {'static_pg': static_page_obj}
