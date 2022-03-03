import os

from decouple import config

from physionet.settings.base import *

ENVIRONMENT = 'production'
DEBUG = False

ALLOWED_HOSTS = ['physionet-production.ecg.mit.edu', 'physionet.org', 'www.physionet.org']
SITE_ID = 3

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

EMAIL_FROM_DOMAINS = ['physionet.org']
DEFAULT_FROM_EMAIL = 'PhysioNet Automated System <noreply@physionet.org>'
CONTACT_EMAIL = 'PhysioNet Contact <contact@physionet.org>'
SERVER_EMAIL = 'PhysioNet System <root@physionet.org>'
CREDENTIAL_EMAIL = 'PhysioNet Credentialing <credentialing@physionet.org>'
ERROR_EMAIL = 'contact@physionet.org'

ADMINS = [('PhysioNet Technical', 'technical@physionet.org')]

GCP_BUCKET_PREFIX = ""

DEMO_FILE_ROOT = os.path.join(os.path.abspath(os.path.join(BASE_DIR, os.pardir)), 'demo-files')

MEDIA_ROOT = '/data/pn-media'

DATACITE_API_URL = 'https://api.datacite.org/dois'

# Tags for the ORCID API
ORCID_DOMAIN = 'https://orcid.org'
ORCID_REDIRECT_URI = 'https://physionet.org/authorcid'
ORCID_AUTH_URL = 'https://orcid.org/oauth/authorize'
ORCID_TOKEN_URL = 'https://orcid.org/oauth/token'

# If defined, MEDIA_X_ACCEL_ALIAS is the virtual URL path
# corresponding to MEDIA_ROOT. If possible, when serving a file
# located in MEDIA_ROOT, the response will use an X-Accel-Redirect
# header so that nginx can serve the file directly.
MEDIA_X_ACCEL_ALIAS = '/protected'

STATIC_ROOT = '/data/pn-static'

if RUNNING_TEST_SUITE:
    MEDIA_ROOT = os.path.join(MEDIA_ROOT, 'test')
    STATIC_ROOT = os.path.join(STATIC_ROOT, 'test')
