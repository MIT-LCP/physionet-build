from django.core.exceptions import ValidationError
from django.utils.html import format_html


class HtmlValidationError(ValidationError):
    """
    Validation error with an HTML message.

    The message consists of a short 'title' optionally followed by a
    longer 'details'.

    Like the standard Django ValidationError, a 'code' can be
    specified.  'params' are not supported; to include additional
    parameters in the message, use django.utils.html.format_html.
    """
    def __init__(self, title, details='', *, code=None):
        message = format_html('<strong>{}</strong>', title)
        if details:
            message += format_html(' {}', details)
        super().__init__(message, code=code)
