import re

from django.core.exceptions import ValidationError


def validate_domain_list(value):
    """
    Validate a list of comma separated email domains ('mit.edu, buffalo.edu, gmail.com').
    """
    if not re.fullmatch(r'(\w+\.\w+,*\s*)*', value):
        raise ValidationError('Must be separated with commas.')
