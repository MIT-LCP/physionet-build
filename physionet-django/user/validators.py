import re

from django.conf import settings
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, validate_email
from django.utils.translation import gettext as _
from zxcvbn import zxcvbn


_subword = re.compile(r'\d+|[^\W\d_]+')

class ComplexityValidator():
    """
    Require at least one symbol
    """
    def __init__(self):
        self.minimum_complexity = 2

    def validate(self, password, user=None):
        # NOTE: Keep list of forbidden words in sync with
        # zxcvbn_ProgressBar_Register.js and
        # zxcvbn_ProgressBar_Change.js

        bad_words = ['physio', 'physionet']

        try:
            fname = user.profile.first_names
            lname = user.profile.last_name
        except AttributeError:
            # new user, profile does not yet exist
            fname = user.first_names
            lname = user.last_name

        bad_words += re.findall(_subword, fname)
        bad_words += re.findall(_subword, lname)
        bad_words += re.findall(_subword, user.email)
        bad_words += re.findall(_subword, user.username)

        info = zxcvbn(password, bad_words)
        if info['score'] < self.minimum_complexity:
            raise ValidationError(
                _("This password is too weak."),
                code='password_weak_password',
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
    """
    Only accept words that start with an alphabetical character followed by
    alphanumeric characters incluiding spaces, underscores, hyphens, and apostrophes.
    """
    if not re.fullmatch(r'[^\W_0-9]([\w\' -])+', value):
        raise ValidationError('Letters, numbers, spaces, underscores, hyphens, and apostrophes only. Must begin with a letter.')


def validate_affiliation(value):
    """
    Validate affiliation that start with an alphabetical characters
    followed by alphanumeric, spaces, underscores, hyphens, and apostrophes
    and the following special characters: ,()/&.
    """
    if not re.fullmatch(r'[a-zA-Z][\w\',()/&. -]+', value) or '..' in value:
        raise ValidationError('Letters, numbers, spaces, apostrophes, underscores and [,()/&.-] characters only. Must begin with a letter.')


def validate_location(value):
    """
    Validate the location that start with an alphabetical character
    followed by alphanumeric characters, spaces, underscores, hyphens,
    apostrophes, periods and commas
    """
    if not re.fullmatch(r'[^\W_0-9]([\w\',. -])+', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter.')


def validate_organization(value):
    """
    Validate the organization that start with an alphanumeric character.
    """
    if not re.fullmatch(r'^[a-zA-Z0-9].*', value):
        raise ValidationError('Must begin with a letter or a number.')


def validate_job_title(value):
    """
    Validate the job title that start with an alphabetical character
    followed by alphanumeric characters, spaces, underscores, hyphens,
    apostrophes, periods and commas
    """
    if not re.fullmatch(r'[^\W_0-9]([\w\',. -])+', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter.')


def validate_city(value):
    """
    Validate the city that start with an alphabetical character
    followed by alphanumeric characters, spaces, underscores, hyphens,
    apostrophes, periods and commas
    """
    if not re.fullmatch(r'[^\W_0-9]([\w\',. -])+', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter.')


def validate_state(value):
    """
    Validate the state that start with an alphabetical character
    followed by alphanumeric characters, spaces, underscores, hyphens,
    apostrophes, periods and commas
    """
    if not re.fullmatch(r'[^\W_0-9]([\w\',. -])+', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter.')


def validate_zipcode(value):
    """
    Validate the zip code that start with an alphabetical character
    followed by alphanumeric characters, spaces, underscores, hyphens,
    apostrophes, periods and commas
    """

    if not re.fullmatch(r'[A-Za-z0-9-][A-Za-z0-9- ]*', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter.')


def validate_suffix(value):
    """
    Validate the suffix that start with an alphanumerical character
    followed by alphanumeric characters, spaces, underscores, hyphens,
    apostrophes, periods and commas. It cannot be all numbers.
    """
    if re.fullmatch(r'[0-9\-+()]*', value):
        raise ValidationError('Cannot be a number.')
    if not re.fullmatch(r'[a-zA-Z0-9][\w\',. -]+', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter or number.')


def validate_training_course(value):
    """
    Validate the training course that start with an alphabetical
    character followed by alphanumeric characters, spaces, underscores,
    hyphens, apostrophes, periods and commas
    """
    if not re.fullmatch(r'[^\W_0-9]([\w\',. -])+', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter.')


def validate_course(value):
    """
    Validate the course that start with an alphanumerical
    character followed by alphanumeric characters, spaces, underscores,
    hyphens, apostrophes, periods and commas.
    """
    if not re.fullmatch(r'[^\W_0-9]([\w\',. -])+', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter.')


def validate_reference_name(value):
    """
    Validate the reference name that start with an
    alphabetical character followed by alphanumeric characters,
    spaces, underscores, hyphens, apostrophes, periods and commas.
    """
    if not re.fullmatch(r'[a-zA-Z][\w\',. -]+', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter.')


def validate_reference_title(value):
    """
    Validate the reference title that start with an
    alphabetical character followed by alphanumeric characters,
    spaces, underscores, hyphens, apostrophes, periods and commas.
    """
    if not re.fullmatch(r'[^\W_0-9]([\w\',. -])+', value):
        raise ValidationError('Letters, numbers, spaces, hyphens, underscores, apostrophes, periods, and commas only. Must begin with a letter.')

def validate_reference_response(value):
    """
    Validate that the reference response starts with a letter or digit.
    """
    if not re.fullmatch(r'\w.*', value, re.DOTALL):
        raise ValidationError('Must begin with a letter or a digit.')


def validate_research_summary(value):
    """
    Validate that the research summary starts with a letter or digit.
    """
    if not re.fullmatch(r'\w.*', value, re.DOTALL):
        raise ValidationError('Must begin with a letter or a digit.')


def validate_nan(value):
    """
    Validation to verify the input is NOT a number.
    """
    if re.fullmatch(r'[0-9\-+()]*', value):
        raise ValidationError('Cannot be a number.')

def validate_orcid_token(value):
    """
    Validation to verify the token returned during
    views/auth_orcid is in the expected format
    """
    if not re.fullmatch(r'^[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12}$', value):
        raise ValidationError('ORCID token is not in expected format.')

def validate_orcid_id(value):
    """
    Validation to verify the ID returned during
    views/auth_orcid is in the expected format
    """
    if not re.fullmatch(r'^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$', value):
        raise ValidationError('ORCID ID is not in expected format.')

# DEPRECATED VALIDATIONS KEPT FOR MIGRATIONS
def validate_alphaplus(value):
    """
    This function has been deprecated, and should NOT be used.
    This function was kept for the moment to not touch the past migrations.
    """
    if not re.fullmatch(r'[\w][\w\ -]*', value):
        raise ValidationError('Letters, numbers, spaces, underscores, and hyphens only. Must begin with a letter or number.')


def validate_alphaplusplus(value):
    """
    This function has been deprecated, and should NOT be used.
    This function was kept for the moment to not touch the past migrations.
    """
    if not re.fullmatch(r'[\w][\'\,\.\w\ -]*', value):
        raise ValidationError('Letters, numbers, spaces, underscores, hyphens, apostrophes, periods, and commas only. Must begin with a letter or number.')


def validate_training_file_size(value):
    """
    Validate the file size of a file.
    """
    if value.size > settings.MAX_TRAINING_REPORT_UPLOAD_SIZE:
        upload_file_size_limit = settings.MAX_TRAINING_REPORT_UPLOAD_SIZE // 1024
        raise ValidationError(f'The maximum file size that can be uploaded is {upload_file_size_limit} KB.')


def validate_institutional_email(value):
    """
    Validate that the email address is from an institutional domain.
    """
    validate_email(value)
    domains = ["yahoo.com", "163.com", "126.com", "outlook.com", "gmail.com", "qq.com", "foxmail.com"]
    if value.split('@')[-1].lower() in domains:
        raise ValidationError('Please provide an academic or institutional email address.')


def is_institutional_email(value):
    """
    Returns True if the email address is from an institutional domain.
    """
    try:
        validate_institutional_email(value)
        return True
    except ValidationError:
        return False


def validate_aws_id(value):
    """"
    Validate an AWS ID.
    """
    aws_id_pattern = r"\b\d{12}\b"
    if value is not None and not re.search(aws_id_pattern, value):
        raise ValidationError(
            "Invalid AWS ID. Please provide a valid AWS ID, which should be a 12-digit number."
        )
