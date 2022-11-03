from django.conf import settings
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from physionet.views import static_view


class StaticpageFallbackMiddleware(MiddlewareMixin):
    """For every request, if the response is anything other than 400,
    return response, else call static_view
    """

    def process_response(self, request, response):
        if response.status_code != 404:
            return response
        try:
            return static_view(request, request.path_info)
        except Http404:
            return response
        except Exception:
            if settings.DEBUG:
                raise
            return response
