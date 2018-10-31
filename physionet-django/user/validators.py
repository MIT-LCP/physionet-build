import re

from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _
from zxcvbn import zxcvbn


class ComplexityValidator():
    """
    Require at least one symbol
    """
    def __init__(self):
        self.minimum_complexity = 2
        self.maximum_complexity = 4

    def validate(self, password, user=None):
        if zxcvbn(password,[])['score'] < self.minimum_complexity:
            raise ValidationError(
                _("This password is too weak."),
                code='password_weak_password',
            )
        elif zxcvbn(password,[])['score'] > self.maximum_complexity:
            raise ValidationError(
                _("This password is incompatible."),
                code='password_incompatible',
            )

    def get_help_text(self):
        return _(
            "Your password is too weak."
        )


class UsernameValidator(UnicodeUsernameValidator):
    regex = r'^[a-zA-Z][a-zA-Z0-9-]{3,49}$'
    message = _(
        'The username must contain 4 to 50 characters. Letters, digits and - only. Must start with a letter.')


def validate_name(value):
    if not re.fullmatch(r'[^\W\d_]([^\W_]|[ -])*', value):
        raise ValidationError('Letters, numbers, spaces, and hyphens only. Must begin with a letter.')

