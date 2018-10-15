import re

from django.core.exceptions import ValidationError


def validate_filename(value):
    """
    Validate file/folder names.

    Examples:
    allowed = ['h', 'hi1', 'hi1.txt', '1.1', 'hi1.x', 'hi_1', '1-hi.1']
    disallowed = ['', '!', 'hi!', '.hi', 'hi.', 'hi..hi', '.', '..']
    """
    if not re.fullmatch(r'\w+([\w\-\.]*\w+)?', value) or '..' in value:
        raise ValidationError('Invalid filename: "%(filename)s" ' \
            'Allowed characters are: numbers, letters, dash, underscore, ' \
            'and dot. Names may not contain adjacent dots, begin with, ' \
            'or end with a dot.', params={'filename':value})
