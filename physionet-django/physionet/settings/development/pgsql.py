from physionet.settings.development.base import *

# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'physionet',
        'USER': 'physionet',
        'PASSWORD': 'password',
        'HOST': 'localhost',
        'PORT': '',
        'TEST': {
            'MIRROR': 'default'
        }
    }
}
