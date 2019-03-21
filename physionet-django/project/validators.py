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


def validate_doi(value):
    """
    Validate a doi. Currently pn is assigned the 10.13026 prefix
    """
    if not re.fullmatch(r'10\.13026/[\w]{5,10}', value):
        raise ValidationError('Invalid DOI: %(doi)s',
            params={'doi':value})


def validate_subdir(value):
    """
    Validate a subdirectory used to explore a project's files.
    Only letters, numbers, dashes, underscores, dots, and / allowed,
    or empty. No consecutive dots or fwd slashes.
    """
    if not re.fullmatch(r'[\w\-\./]*', value) or '..' in value or value.startswith('/') or '//' in value:
        raise ValidationError('Invalid path')


def validate_version(value):
    """
    Validate version string. Allow empty value for initial state.
    """
    if value:
        if not re.fullmatch(r'[0-9]+(\.[0-9]+)*', value) or '..' in value:
            raise ValidationError('Version may only contain numbers and dots, and must begin and end with a number.')
