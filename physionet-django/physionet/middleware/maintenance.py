import functools
import logging

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.shortcuts import render
from django.utils.log import log_response


LOGGER = logging.getLogger(__name__)

SAFE_HTTP_METHODS = ('GET', 'HEAD', 'OPTIONS', 'TRACE')

ERROR_TEMPLATE = 'site_maintenance.html'


class SystemMaintenanceMiddleware:
    """
    Middleware that disables editing during system maintenance.

    This middleware class can be used when the system is undergoing
    maintenance; it attempts to prevent actions that could make
    changes on the server side, making the site "read-only" from a
    visitor's perspective.  This may either be enabled permanently (to
    operate as an "emergency fallback" server), or temporarily (to
    freeze the site so that it can be migrated to a replica without
    loss of data.)

    If settings.SYSTEM_MAINTENANCE_NO_CHANGES is true, all HTTP
    requests other than GET, HEAD, OPTIONS, and TRACE are disallowed,
    except for views decorated with 'allow_post_during_maintenance'.

    Disallowed requests will result in an error page with a status of
    '503 Service Unavailable'.  If the SYSTEM_MAINTENANCE_MESSAGE
    setting is nonempty, that defines an HTML message that will be
    displayed on the error page.
    """
    def __init__(self, get_response):
        # Initialize middleware.  get_response is the next middleware
        # in the chain, which should be called by __call__.  If this
        # raises MiddlewareNotUsed, the middleware is removed from the
        # chain and has no effect.
        self.get_response = get_response

        if settings.SYSTEM_MAINTENANCE_NO_CHANGES:
            LOGGER.warning(
                'SYSTEM_MAINTENANCE_NO_CHANGES enabled.  Message: {}'.format(
                    settings.SYSTEM_MAINTENANCE_MESSAGE))
        elif settings.SYSTEM_MAINTENANCE_NO_UPLOAD:
            LOGGER.warning(
                'SYSTEM_MAINTENANCE_NO_UPLOAD enabled.  Message: {}'.format(
                    settings.SYSTEM_MAINTENANCE_MESSAGE))
        else:
            raise MiddlewareNotUsed()

    def __call__(self, request):
        # Process a request and invoke the next middleware in the chain.
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Prepare to invoke a view function with the given request and
        # arguments.  If this returns None, the view will be invoked
        # as usual; if it returns a response, the view is bypassed and
        # the given response is returned instead.
        if not settings.SYSTEM_MAINTENANCE_NO_CHANGES:
            return None
        elif request.method in SAFE_HTTP_METHODS:
            return None
        elif hasattr(view_func, 'view_allow_post_during_maintenance'):
            return None
        else:
            return self._reject(request)

    def process_exception(self, request, exception):
        # Handle an exception raised by a view.  If this returns None,
        # the default exception handling is used; if it returns a
        # response, that response is used instead.
        if isinstance(exception, ServiceUnavailable):
            return self._reject(request)
        else:
            return None

    def _reject(self, request):
        return service_unavailable(request)


class ServiceUnavailable(Exception):
    """
    Exception indicating an action is impossible due to maintenance.

    This exception should be raised by a view if the requested action
    is disallowed because of settings.SYSTEM_MAINTENANCE_NO_CHANGES or
    settings.SYSTEM_MAINTENANCE_NO_UPLOAD.
    """
    pass


def service_unavailable(request):
    """
    Generate a '503 Service Unavailable' error page.
    """
    response = render(request, ERROR_TEMPLATE, {
        'maintenance_message': settings.SYSTEM_MAINTENANCE_MESSAGE,
    }, status=503)

    # Invoke log_response manually (causing the default logging to be
    # skipped), since otherwise Django will treat a 503 status as an
    # error requiring a verbose log message and email to admins
    log_response(
        'Service Unavailable: %s', request.path,
        request=request,
        response=response,
        level='warning',
    )
    return response


def allow_post_during_maintenance(view_func):
    """
    Decorator for views that may accept POSTs during maintenance.

    This means that when SYSTEM_MAINTENANCE_NO_CHANGES is set, the
    view may receive POST and other "stateful" HTTP requests, which
    would normally be disallowed.

    It should be understood that if maintenance mode is active,
    changes made to the database and/or filesystem might not be
    persistent, so this decorator should seldom be used.
    """
    @functools.wraps(view_func)
    def wrapped_view(*args, **kwargs):
        return view_func(*args, **kwargs)
    wrapped_view.view_allow_post_during_maintenance = True
    return wrapped_view


def disallow_during_maintenance(view_func):
    """
    Decorator for views that are disabled during maintenance.

    This means that when SYSTEM_MAINTENANCE_NO_CHANGES is set, the
    view always returns an error page with a status of "503 Service
    Unavailable".
    """
    @functools.wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if settings.SYSTEM_MAINTENANCE_NO_CHANGES:
            raise ServiceUnavailable()
        return view_func(*args, **kwargs)
    return wrapped_view
