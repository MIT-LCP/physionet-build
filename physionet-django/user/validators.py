from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _
from zxcvbn import zxcvbn
import re

class ComplexityValidator(object):
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

class MaximumLengthValidator(object):
    """
    Validate whether the password is too long
    """
    def __init__(self, max_length=25):
        self.max_length = max_length

    def validate(self, password, user=None):
        if len(password) > self.max_length:
            raise ValidationError(
                _("This password must be no more than %(max_length)d characters."),
                code='password_too_long',
                params={'max_length': self.max_length},
            )

    def get_help_text(self):
        return _(
            "Your password cannot contain more than %(max_length)d characters."
            % {'max_length': self.max_length}
        )


class AlphabeticRequirementValidator(object):
    """
    Require at least one upper-case and one lower-case alphabetic character
    """
    def validate(self, password, user=None):
        if password.upper() == password.lower():
            raise ValidationError(
                _("This password must contain at least one upper-case and one lower-case letter."),
                code='password_no_alphabetics',
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least one upper-case and one lower-case letter."
        )


class NumericRequirementValidator(object):
    """
    Require at least one numerical digit
    """
    def __init__(self):
        super(NumericRequirementValidator, self).__init__()
        self.rx_numeric = re.compile(r'\d')

    def validate(self, password, user=None):
        if not bool(self.rx_numeric.search(password)):
            raise ValidationError(
                _("This password must contain at least one numeric character."),
                code='password_no_numerics',
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least one numeric character."
        )


class SymbolicRequirementValidator(object):
    """
    Require at least one symbol
    """
    def __init__(self):
        super(SymbolicRequirementValidator, self).__init__()
        self.rx_symbol = re.compile(r"""[~!@#$%&^*?'"<>]""")

    def validate(self, password, user=None):
        if not bool(self.rx_symbol.search(password)):
            raise ValidationError(
                _("This password must contain at least one special character."),
                code='password_no_symbols',
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least one symbol."
        )


class MixedCharacterValidator(AlphabeticRequirementValidator,
    NumericRequirementValidator, SymbolicRequirementValidator):
    """
    Combining minimum alphabetic, numeric, and symbolic character requirements
    """

    def __init__(self):
        super(MixedCharacterValidator, self).__init__()

    def validate(self, password, user=None):
        for cls in MixedCharacterValidator.__bases__:
            cls.validate(self, password, user)

    def get_help_text(self):
        return _(
            "Your password must contain a mixture of letters, numbers, and symbols."
        )

class UsernameValidator(UnicodeUsernameValidator):
    regex = r'^[a-zA-Z0-9-]+$'
    message = _(
        'Enter a valid username. This value may contain only letters, '
                "numbers, and - character.")
