"""
Django settings for physionet project.

Generated by 'django-admin startproject' using Django 1.11.5.

For more information on this file, see
https://docs.djangoproject.com/en/1.11/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.11/ref/settings/
"""

import fcntl
import sys
import os

from decouple import config

import logging.config

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Customisable platform settings
PLATFORM_NAME = 'PhysioNet'

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/

SECRET_KEY = config('SECRET_KEY')


# Application definition

INSTALLED_APPS = [
    'dal',
    'dal_select2',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    'ckeditor',
    # 'django_cron',
    'background_task',

    'user',
    'project',
    'console',
    'export',
    'notification',
    'search',
    'lightwave',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CRON_CLASSES = [
    "physionet.cron.RemoveUnverifiedEmails",
    "physionet.cron.RemoveOutstandingInvites",
]

ROOT_URLCONF = 'physionet.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR,'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'physionet.wsgi.application'

# Session management

SESSION_COOKIE_SECURE = True

# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'user.validators.ComplexityValidator',
    },
]

AUTHENTICATION_BACKENDS = ['user.models.DualAuthModelBackend']

AUTH_USER_MODEL = 'user.User'

LOGIN_URL = '/login/'

LOGIN_REDIRECT_URL = '/projects/'

LOGOUT_REDIRECT_URL = '/'

# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/New_York'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Django background tasks max attempts
MAX_ATTEMPTS = 5

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR,'static')]
# Google Storge service account credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(BASE_DIR, 'PhysioNet-Data-credentials.json')

# Google G suite Groups service account and Private Key file
SERVICE_ACCOUNT_EMAIL = 'gcp-physionet-groups@physionet-data.iam.gserviceaccount.com'

SERVICE_ACCOUNT_PKCS12_FILE_PATH = os.path.join(BASE_DIR, 'PhysioNet-Data-credentials.p12')

GCP_DELEGATION_EMAIL = config('GCP_DELEGATION_EMAIL', default=False)
GCP_SECRET_KEY = config('GCP_SECRET_KEY', default=False)

GCP_BUCKET_PREFIX = "testing-delete."
GCP_DOMAIN = "physionet.org"

# Header tags for the AWS lambda function that grants access to S3 storage
AWS_HEADER_KEY = config('AWS_KEY', default=False)
AWS_HEADER_VALUE = config('AWS_VALUE', default=False)
AWS_HEADER_KEY2 = config('AWS_KEY2', default=False)
AWS_HEADER_VALUE2 = config('AWS_VALUE2', default=False)
AWS_CLOUD_FORMATION = config('AWS_CLOUD_FORMATION', default=False)

# Tags for the DataCite API used for DOI
DATACITE_API_URL = 'https://api.test.datacite.org/dois'
DATACITE_PREFIX = config('DATACITE_TEST_PREFIX', default=False)
DATACITE_USER = config('DATACITE_TEST_USER', default=False)
DATACITE_PASS = config('DATACITE_TEST_PASS', default=False)

# Used to verify if we are running in the production environment
PRODUCTION = False

# List of permitted HTML tags and attributes for rich text fields.
# The 'default' configuration permits all of the tags below.  Other
# configurations may be added that permit different sets of tags.

# Attributes that can be added to any HTML tag
_generic_attributes = ['lang', 'title']

# Inline/phrasing content
_inline_tags = {
    'a':      {'attributes': ['href']},
    'abbr':   True,
    'b':      True,
    'bdi':    True,
    'cite':   True,
    'code':   True,
    'dfn':    True,
    'em':     True,
    'i':      True,
    'kbd':    True,
    'q':      True,
    'rb':     True,
    'rp':     True,
    'rt':     True,
    'rtc':    True,
    'ruby':   True,
    's':      True,
    'samp':   True,
    'span':   True,
    'strong': True,
    'sub':    True,
    'sup':    True,
    'time':   True,
    'u':      True,
    'var':    True,
    'wbr':    True,
    'img':    {'attributes': ['alt', 'src', 'height', 'width']},
}
# Block/flow content
_block_tags = {
    # Paragraphs, lists, quotes, line breaks
    'blockquote': True,
    'br':         True,
    'dd':         True,
    'div':        True,
    'dl':         True,
    'dt':         True,
    'li':         {'attributes': ['value']},
    'ol':         {'attributes': ['start', 'type']},
    'p':          True,
    'pre':        True,
    'ul':         True,

    # Tables
    'caption':    True,
    'col':        {'attributes': ['span']},
    'colgroup':   {'attributes': ['span']},
    'table':      {'attributes': ['width']},
    'tbody':      True,
    'td':         {'attributes': ['colspan', 'headers', 'rowspan', 'style'],
                   'styles': ['text-align']},
    'tfoot':      True,
    'th':         {'attributes': ['abbr', 'colspan', 'headers', 'rowspan',
                                  'scope', 'sorted', 'style'],
                   'styles': ['text-align']},
    'thead':      True,
    'tr':         True,
}
# Math content (inline or block)
_math_tags = {
    'math':          {'attributes': ['alttext', 'display']},
    'annotation':    {'attributes': ['encoding']},
    'semantics':     True,

    'maligngroup':   {'attributes': ['groupalign']},
    'malignmark':    {'attributes': ['edge']},
    'menclose':      {'attributes': ['notation']},
    'merror':        True,
    'mfenced':       {'attributes': ['close', 'open', 'separators']},
    'mfrac':         {'attributes': [
        'bevelled', 'numalign', 'denomalign', 'linethickness']},
    'mi':            {'attributes': ['class', 'mathsize', 'mathvariant']},
    'mlabeledtr':    {'attributes': ['rowalign', 'columnalign', 'groupalign']},
    'mmultiscripts': True,
    'mn':            {'attributes': ['class', 'mathsize', 'mathvariant']},
    'mo':            {'attributes': [
        'class', 'accent', 'fence', 'form', 'largeop', 'linebreak',
        'linebreakmultchar', 'linebreakstyle', 'lspace', 'mathsize',
        'mathvariant', 'maxsize', 'minsize', 'movablelimits', 'rspace',
        'separator', 'stretchy', 'symmetric']},
    'mover':         {'attributes': ['accent', 'align']},
    'mpadded':       {'attributes': [
        'depth', 'height', 'lspace', 'voffset', 'width']},
    'mphantom':      True,
    'mprescripts':   True,
    'mroot':         True,
    'mrow':          {'attributes': ['class']},
    'ms':            {'attributes': ['lquote', 'rquote']},
    'mspace':        {'attributes': ['width', 'height', 'depth', 'linebreak']},
    'msqrt':         True,
    'mstyle':        {'attributes': [
        'decimalpoint', 'displaystyle', 'infixlinebreakstyle', 'mathsize',
        'mathvariant', 'scriptlevel', 'scriptsizemultiplier']},
    'msub':          True,
    'msubsup':       True,
    'msup':          True,
    'mtable':        {'attributes': [
        'align', 'alignmentscope', 'columnalign', 'columnlines',
        'columnspacing', 'columnwidth', 'displaystyle', 'equalcolumns',
        'equalrows', 'frame', 'groupalign', 'rowalign', 'rowlines',
        'rowspacing', 'side', 'width']},
    'mtd':           {'attributes': [
        'rowspan', 'columnspan', 'rowalign', 'columnalign', 'groupalign']},
    'mtext':         {'attributes': ['class', 'mathsize', 'mathvariant']},
    'mtr':           {'attributes': ['rowalign', 'columnalign', 'groupalign']},
    'munder':        {'attributes': ['accentunder', 'align']},
    'munderover':    {'attributes': ['accent', 'accentunder', 'align']},
    'none':          True,
}
# Classes used by MathJax (see toMathMLclass() in extensions/toMathML.js)
_math_classes = [
    'MJX-TeXAtom-ORD', 'MJX-TeXAtom-OP', 'MJX-TeXAtom-BIN', 'MJX-TeXAtom-REL',
    'MJX-TeXAtom-OPEN', 'MJX-TeXAtom-CLOSE', 'MJX-TeXAtom-PUNCT',
    'MJX-TeXAtom-INNER', 'MJX-TeXAtom-VCENTER',
    'MJX-fixedlimits', 'MJX-variant',
    'MJX-tex-caligraphic', 'MJX-tex-caligraphic-bold', 'MJX-tex-oldstyle',
    'MJX-tex-oldstyle-bold', 'MJX-tex-mathit',
]

CKEDITOR_CONFIGS = {
    'default': {
        'toolbar': 'Custom',
        'toolbar_Custom': [
            ['Format'],
            ['Bold', 'Italic', 'Underline','Blockquote'],
            ['NumberedList', 'BulletedList'],
            ['InlineEquation', 'BlockEquation', 'CodeSnippet', 'Table'],
            ['Link', 'Unlink'],
            ['RemoveFormat', 'Source'],
        ],
        'removeDialogTabs': 'link:advanced',
        'disableNativeSpellChecker': False,
        'width': '100%',

        # Show options "Heading 2" to "Heading 4" in the format menu,
        # but map these to <h3>, <h4>, <h5> tags
        'format_tags': 'p;h2;h3;h4',
        'format_h2': {'element': 'h3'},
        'format_h3': {'element': 'h4'},
        'format_h4': {'element': 'h5'},

        'extraPlugins': 'codesnippet,pnmathml',
        'allowedContent': {
            **_inline_tags,
            **_block_tags,
            **_math_tags,
            'h3': True,
            'h4': True,
            'h5': True,
            'h6': True,
            '*': {'attributes': _generic_attributes,
                  'classes': _math_classes},
        },
        'mathJaxLib': ('/static/mathjax/MathJax.js'
                       '?config=TeX-AMS-MML_HTMLorMML-full'),
    }

}

# True if the program is invoked as 'manage.py test'
RUNNING_TEST_SUITE = (len(sys.argv) > 1 and sys.argv[1] == 'test')

LOGGING_CONFIG = None
LOGLEVEL = os.environ.get('LOGLEVEL', 'info').upper()

if RUNNING_TEST_SUITE:
    _logfile = open(os.path.join(BASE_DIR, 'test.log'), 'w')
else:
    _logfile = sys.stderr

logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'formatters': {
        'console': {
            'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        },
        'simple': {
            'format': '%(levelname)s %(asctime)-15s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console',
            'stream': _logfile,
        },
        'Custom_Logging': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'stream': _logfile,
        },
        'verbose_console': {
            'class': 'physionet.log.VerboseStreamHandler',
            'formatter': 'console',
            'stream': _logfile,
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'physionet.log.SaferAdminEmailHandler',
        },
    },
    'loggers': {
        '': {
            'level': 'INFO',
            'handlers': ['console'],
        },
        'user': {
            'level': 'INFO',
            'handlers': ['Custom_Logging'],
            'propagate': False,
        },
        'django.security.DisallowedHost': {
            'handlers': ['mail_admins'],
            'level': 'CRITICAL',
            'propagate': False,
        },
       'django.request': {
            'handlers': ['verbose_console', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'physionet.error': {
            'handlers': ['console', 'mail_admins', 'Custom_Logging'],
            'level': 'ERROR',
        }
    },
})

# If this environment variable is set, acquire a shared lock on the
# named file.  The file descriptor is left open, but is
# non-inheritable (close-on-exec), so the lock will be inherited by
# forked child processes, but not by execed programs.
if os.getenv('PHYSIONET_LOCK_FILE'):
    _lockfd = os.open(os.getenv('PHYSIONET_LOCK_FILE'),
                      os.O_RDWR | os.O_CREAT, 0o660)
    # Note that Python has at least three different ways of locking
    # files.  We want fcntl.flock (i.e. flock(2)), which is tied to
    # the file desciptor and inherited by child processes.  In
    # contrast, fcntl.lockf uses fcntl(2) and os.lockf uses lockf(3),
    # both of which are tied to the PID.
    fcntl.flock(_lockfd, fcntl.LOCK_SH)
