"""
WSGI config for project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.11/howto/deployment/wsgi/
"""

import os

from django.core.signals import request_started, request_finished
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "physionet.settings.development.sqlite")

application = get_wsgi_application()

# If we are running under uWSGI, then store the current request path
# in the process name (which can be seen with 'ps ax'.)
try:
    from uwsgi import setprocname
except ImportError:
    pass
else:
    def set_process_name_for_request(sender, environ, **kwargs):
        path = environ.get('PATH_INFO', '<unknown>')
        setprocname('uwsgi ' + path)

    def unset_process_name(sender, **kwargs):
        setprocname('uwsgi (idle)')

    request_started.connect(set_process_name_for_request)
    request_finished.connect(unset_process_name)
