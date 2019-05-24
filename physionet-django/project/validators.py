import re

from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _

_good_name_pattern = re.compile(r'\w+([\w\-\.]*\w+)?', re.ASCII)
_bad_name_pattern = re.compile(r'^(?:con|nul|aux|prn|com\d|lpt\d)(?:\.|$)',
                               re.ASCII|re.IGNORECASE)


def validate_filename(value):
    """
    Validate file/folder names.

    Examples:
    allowed = ['h', 'hi1', 'hi1.txt', '1.1', 'hi1.x', 'hi_1', '1-hi.1']
    disallowed = ['', '!', 'hi!', '.hi', 'hi.', 'hi..hi', '.', '..']
    """
    if not _good_name_pattern.fullmatch(value):
        raise ValidationError(
            'Invalid file name "%(filename)s". '
            'File names may only contain letters, numbers, dashes (-), dots '
            '(.), and underscores (_). They may not begin or end with a dot '
            'or dash.',
            params={'filename': value})
    if '..' in value:
        raise ValidationError(
            'Invalid file name "%(filename)s". '
            'File names may not contain two consecutive dots.',
            params={'filename': value})
    if _bad_name_pattern.match(value):
        raise ValidationError(
            'Invalid file name "%(filename)s". '
            'File names CON, NUL, AUX, PRN, COM0-COM9, LPT0-LPT9, or any of '
            'these followed by a dot and file extension, are not allowed.',
            params={'filename': value})


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


def validate_slug(value):
    """
    Validate a published slug. Not ending with dash number for google
    cloud.
    """
    if (not re.fullmatch(r'[a-z0-9](?:[a-z0-9\-]{0,18}[a-z0-9])?', value)
            or '--' in value or re.fullmatch(r'.+\-[0-9]+', value)):
        raise ValidationError((
            'Slug must only contain lowercase alphanumerics and hyphens, of '
            'length 1-20. Must begin and end with an alphanumeric. Must not '
            'contain consecutive hyphens or end with hypen number.'))
