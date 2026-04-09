import unicodedata

from django.core.exceptions import ValidationError
from django.db import models


class DUASignature(models.Model):
    """
    Log of user signing DUA
    """
    project = models.ForeignKey('project.PublishedProject',
        on_delete=models.CASCADE)
    user = models.ForeignKey('user.User', on_delete=models.CASCADE,
                             related_name='dua_signatures')
    sign_datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()

    @staticmethod
    def get_user_initials(user):
        """Get initials from user's profile name."""
        initials = ''
        if user.profile.first_names:
            for name in user.profile.first_names.split():
                if name:
                    initials += name[0].upper()
        if user.profile.last_name:
            initials += user.profile.last_name[0].upper()
        return initials

    @staticmethod
    def normalize_for_comparison(text):
        """Normalize text for Unicode-aware case-insensitive comparison."""
        return unicodedata.normalize('NFKD', text.casefold())

    @staticmethod
    def validate_signature_initials(user, initials):
        if not initials or not initials.strip():
            raise ValidationError('You must enter your initials to sign the agreement.')
        expected_initials = DUASignature.get_user_initials(user)
        if DUASignature.normalize_for_comparison(initials.strip()) != \
                DUASignature.normalize_for_comparison(expected_initials):
            raise ValidationError(
                f'The initials entered do not match. Please enter: {expected_initials}'
            )
