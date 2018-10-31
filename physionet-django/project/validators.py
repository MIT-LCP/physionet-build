import re

from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _


def validate_filename(value):
    """
    Validate file/folder names.

    Examples:
    allowed = ['h', 'hi1', 'hi1.txt', '1.1', 'hi1.x', 'hi_1', '1-hi.1']
    disallowed = ['', '!', 'hi!', '.hi', 'hi.', 'hi..hi', '.', '..']
    """
    if not re.fullmatch(r'\w+([\w\-\.]*\w+)?', value) or '..' in value:
        raise ValidationError('Invalid filename: "%(filename)s" ' \
            'Filenames may only contain letters, numbers, dashes, underscores, ' \
            'and dots. They may not contain adjacent dots, begin with, ' \
            'or end with a dot.', params={'filename':value})


def validate_alphaplus(value):
    if not re.fullmatch(r'[a-zA-Z0-9][\w\ -]*', value):
        raise ValidationError('Letters, numbers, spaces, underscores, and hyphens only. Must begin with a letter or number.')

