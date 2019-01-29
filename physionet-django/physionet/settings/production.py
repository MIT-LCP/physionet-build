import sys

from decouple import config

from .base import *

DEBUG = True

ALLOWED_HOSTS = ['alpha.physionet.org', 'production-physionet.ecg.mit.edu']

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


DEMO_FILE_ROOT = os.path.join(os.path.abspath(os.path.join(BASE_DIR, os.pardir)), 'demo-files')

MEDIA_ROOT = '/data/pn-media'

STATIC_ROOT = '/data/pn-static'

if len(sys.argv) > 1 and sys.argv[1] == 'test':
    MEDIA_ROOT = os.path.join(MEDIA_ROOT, 'test')
    STATIC_ROOT = os.path.join(STATIC_ROOT, 'test')
