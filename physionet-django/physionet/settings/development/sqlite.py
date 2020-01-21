import os
from physionet.settings.base import *

DEBUG = True
SESSION_COOKIE_SECURE = False

ALLOWED_HOSTS = ['*']

INSTALLED_APPS += [
    'debug_toolbar',
    'django.contrib.sites',
]
SITE_ID = 4

MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware', ]

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = 'PhysioNet Automated System <noreply@dev.physionet.org>'
CONTACT_EMAIL = 'PhysioNet Contact <contact@dev.physionet.org>'
SERVER_EMAIL = 'PhysioNet System <root@dev.physionet.org>'

ADMINS = [('PhysioNet Technical', 'technical@dev.physionet.org')]

DEBUG_TOOLBAR_CONFIG = {
    'JQUERY_URL': '',
}

# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'physionet.db.chaotic.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
        'TEST': {
            'MIRROR': 'default'
        }
    }
}

DEMO_FILE_ROOT = os.path.join(os.path.abspath(os.path.join(BASE_DIR, os.pardir)), 'demo-files')

MEDIA_ROOT = os.path.join(os.path.abspath(os.path.join(BASE_DIR, os.pardir)), 'media')

# If defined, MEDIA_X_ACCEL_ALIAS is the virtual URL path
# corresponding to MEDIA_ROOT. If possible, when serving a file
# located in MEDIA_ROOT, the response will use an X-Accel-Redirect
# header so that nginx can serve the file directly.
MEDIA_X_ACCEL_ALIAS = None

if RUNNING_TEST_SUITE:
    MEDIA_ROOT = os.path.join(MEDIA_ROOT, 'test')
    STATICFILES_DIRS[0] = os.path.join(STATICFILES_DIRS[0], 'test')
