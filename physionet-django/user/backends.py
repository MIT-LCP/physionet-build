import logging

from django.contrib.auth.backends import ModelBackend, BaseBackend

from user.models import User

logger = logging.getLogger(__name__)


class DualAuthModelBackend(ModelBackend):
    """
    This is a ModelBacked that allows authentication with either a username or an email address.
    """
    def authenticate(self, request, username=None, password=None):
        # After implementation of OAuth2, (presumably) many crawlers started to attempt
        # authentication with tokens, causing server errors due to the comparison below.
        if username is None:
            return None
        if '@' in username:
            kwargs = {'email': username.lower()}
        else:
            kwargs = {'username': username.lower()}
        try:
            user = User.objects.get(**kwargs)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            logger.error('Unsuccessful authentication {0}'.format(username.lower()))
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class OrcidAuthBackend(BaseBackend):
    """
    This is a Base that allows authentication with orcid_profile.
    """
    def authenticate(self, request, orcid_profile=None):
        if orcid_profile is None:
            return None

        user = orcid_profile.user
        return user if self.user_can_authenticate(user) else None

    def user_can_authenticate(self, user):
        is_active = getattr(user, 'is_active', None)
        return is_active or is_active is None


    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
