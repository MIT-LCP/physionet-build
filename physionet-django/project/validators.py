import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

MAX_FILENAME_LENGTH = 100
MAX_PROJECT_SLUG_LENGTH = 30
MAX_GCS_OBJECT_NAME_LENGTH = 256

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
    if len(value) > MAX_FILENAME_LENGTH:
        raise ValidationError(
            'Invalid file name "%(filename)s". '
            'File names may be at most %(limit)s characters long.',
            params={'filename': value, 'limit': MAX_FILENAME_LENGTH})
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


def validate_filename_or_parent(value):
    """
    Check if string is either a valid file base name, or '../'.
    """
    if value != '../':
        validate_filename(value)


def validate_oldfilename(value):
    """
    Check if string is potentially a file base name.
    """
    if '/' in value or value == '' or value == '.' or value == '..':
        raise ValidationError('Not a valid file base name.')


def validate_doi(value):
    """
    Validate a doi.
    This follows the regular expression in the DataCite website.

    https://support.datacite.org/docs/doi-basics
    """
    if not re.fullmatch(r'^10.\d{4,9}/[-._;()/:a-zA-Z0-9]+$', value):
        raise ValidationError('Invalid DOI: %(doi)s', params={'doi': value})


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
    if not re.fullmatch(r'[0-9]+(\.[0-9]+)+', value) or '..' in value:
        raise ValidationError('Version may only contain numbers and dots, and must begin and end with a number.')
    if re.fullmatch(r'[0.]+', value):
        raise ValidationError('Version must not be entirely zeroes.')
    if re.search(r'\b0[0-9]', value):
        raise ValidationError('Version must not contain leading zeroes. '
                              'For example, write "1.0.1" instead of "1.00.01".')


def validate_slug(value):
    """
    Validate a published slug. Not ending with dash number for google
    cloud. Must not exceed MAX_PROJECT_SLUG_LENGTH.

    Only accepts lowercase alphanumerics and hyphens
    """
    if len(value) > MAX_PROJECT_SLUG_LENGTH:
        raise ValidationError(
            'Invalid file name "%(slug)s". '
            'Slug may be at most %(limit)s characters long.',
            params={'slug': value, 'limit': MAX_PROJECT_SLUG_LENGTH})
    if (not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', value) or '--' in value):
        raise ValidationError("""
            Slug must only contain lowercase alphanumerics and hyphens, and
            must be of length 1-{}. Must begin and end with an alphanumeric.
            Must not contain consecutive hyphens.
            """.format(MAX_PROJECT_SLUG_LENGTH))


def validate_title(value):
    """
    Validate titles that start with an alphanumeric character followed by
    characters marked as letters in Unicode along side with the following
    special characters: ' , * ? : ( ) -
    """
    if not re.fullmatch(r'[a-zA-Z0-9][\w\'*,?:( )-/]+', value):
        raise ValidationError("Enter a valid title. This value may contain only letters, numbers, spaces and "
                              "[,-'*?:/()]")


def validate_topic(value):
    """
    Validate topics that start with an alphabetical character
    followed by characters marked as letters in Unicode and dashes.
    """
    if not re.fullmatch(r'[a-zA-Z\d][\w -]*', value):
        raise ValidationError('Letters, numbers, spaces, underscores, and hyphens only. Must begin with a letter or number.')


def validate_gcs_bucket_object(filename, size):
    """
    Validate a filename and size for upload to gcs bucket objects.

    File names may be at most 256 characters long.
    Only letters, numbers, dashes, underscores, dots, and / allowed,
    or empty. No consecutive dots or fwd slashes.

    File size cannot be negative.
    """
    if not filename or not size:
        raise ValidationError('You must provide the filename and the size.')

    if not size.isnumeric():
        raise ValidationError('The size must be a numeric value.')

    size = int(size)
    if size <= 0:
        raise ValidationError('The file size cannot be a negative value.')

    if len(filename) > MAX_GCS_OBJECT_NAME_LENGTH:
        raise ValidationError(
            f'Invalid file name "{filename}". '
            f'File names may be at most {MAX_GCS_OBJECT_NAME_LENGTH} characters long.'
        )

    if filename[0] != '/':
        raise ValidationError(
            f'Invalid file name "{filename}". '
            'File names must start with a forward slash.'
        )

    for path_segment in filename[1:].split('/'):
        validate_filename(path_segment)
