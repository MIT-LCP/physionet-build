import os
import pathlib

from decouple import config

from physionet.settings.base import *

ALLOWED_HOSTS = config('ALLOWED_HOSTS').split(',')
INTERNAL_IPS = config('INTERNAL_IPS', default='').split(',')
SITE_ID = config('SITE_ID', cast=int)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': '',
        'TEST': {
            'MIRROR': 'default'
        },
    }
}

if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']

    if ENVIRONMENT == 'development' and not RUNNING_TEST_SUITE:
        DEBUG_TOOLBAR_CONFIG = {'SHOW_TOOLBAR_CALLBACK': 'physionet.settings.settings.show_toolbar'}
        def show_toolbar(request):
            return True

# When ready, use the following:
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='localhost')
EMAIL_PORT = config('EMAIL_PORT', default=25, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=False, cast=bool)

EMAIL_FROM_DOMAINS = ['physionet.org']
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='PhysioNet Automated System <noreply@physionet.org>')
CONTACT_EMAIL = config('CONTACT_EMAIL', default='PhysioNet Contact <contact@physionet.org>')
SERVER_EMAIL = config('SERVER_EMAIL', default='PhysioNet System <root@physionet.org>')
CREDENTIAL_EMAIL = config('CREDENTIAL_EMAIL', default='PhysioNet Credentialing <credentialing@physionet.org>')
ERROR_EMAIL = config('ERROR_EMAIL', default='contact@physionet.org')


ADMINS = [(config('ADMINS_NAME', default='PhysioNet Technical'),
           config('ADMINS_MAIL', default='technical@dev.physionet.org'))]

GCP_BUCKET_PREFIX = config('GCP_BUCKET_PREFIX', default='')

DEMO_FILE_ROOT = os.path.join(os.path.abspath(os.path.join(BASE_DIR, os.pardir)), 'demo-files')

MEDIA_ROOT = config('MEDIA_ROOT', default=str((pathlib.Path(BASE_DIR).parent / 'media').resolve()))

# If defined, MEDIA_X_ACCEL_ALIAS is the virtual URL path
# corresponding to MEDIA_ROOT. If possible, when serving a file
# located in MEDIA_ROOT, the response will use an X-Accel-Redirect
# header so that nginx can serve the file directly.
MEDIA_X_ACCEL_ALIAS = config('MEDIA_X_ACCEL_ALIAS', default=None)

STATIC_ROOT = config('STATIC_ROOT', default='')

if RUNNING_TEST_SUITE:
    MEDIA_ROOT = os.path.join(MEDIA_ROOT, 'test')
    STATIC_ROOT = os.path.join(STATIC_ROOT, 'test')
