import sys
import os

from decouple import config

from .base import *

DEBUG = False

ALLOWED_HOSTS = ['alpha.physionet.org', 'physionet-production.ecg.mit.edu', 'physionet.org', 'www.physionet.org']
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'physionet',
        'USER': 'physionet',
        'PASSWORD': config('DATABASES_PASSWORD'),
        'HOST': 'localhost',
        'PORT': '',
    }
}

# When ready, use the following:
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'localhost'
EMAIL_PORT = 25
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
EMAIL_USE_TLS = False

DEFAULT_FROM_EMAIL = 'PhysioNet Automated System <noreply@alpha.physionet.org>'
CONTACT_EMAIL = 'PhysioNet Contact <contact@alpha.physionet.org>'
SERVER_EMAIL = 'PhysioNet System <root@alpha.physionet.org>'

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(BASE_DIR, 'PhysioNet-Data-credentials.json')

ADMINS = [('PhysioNet Technical', 'technical@alpha.physionet.org')]

DEMO_FILE_ROOT = os.path.join(os.path.abspath(os.path.join(BASE_DIR, os.pardir)), 'demo-files')

MEDIA_ROOT = '/data/pn-media'

QUOTA = True

# If defined, MEDIA_X_ACCEL_ALIAS is the virtual URL path
# corresponding to MEDIA_ROOT. If possible, when serving a file
# located in MEDIA_ROOT, the response will use an X-Accel-Redirect
# header so that nginx can serve the file directly.
MEDIA_X_ACCEL_ALIAS = '/protected'

STATIC_ROOT = '/data/pn-static'

if len(sys.argv) > 1 and sys.argv[1] == 'test':
    MEDIA_ROOT = os.path.join(MEDIA_ROOT, 'test')
    STATIC_ROOT = os.path.join(STATIC_ROOT, 'test')
