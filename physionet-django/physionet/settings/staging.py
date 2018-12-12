from decouple import config

from .base import *

DEBUG = True

ALLOWED_HOSTS = ['staging.physionet.org', 'physionet-staging.ecg.mit.edu']

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
EMAIL_HOST = 'mail.ecg.mit.edu'
EMAIL_PORT = 25
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
EMAIL_USE_TLS = False

DEFAULT_FROM_EMAIL = 'PhysioNet Automated System <noreply@staging.physionet.org>'
CONTACT_EMAIL = 'PhysioNet Contact <contact@staging.physionet.org>'

MEDIA_ROOT = '/physionet/media'

STATIC_ROOT = '/physionet/static'
