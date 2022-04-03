import logging

from django.contrib.auth.backends import ModelBackend

from user.models import User

logger = logging.getLogger(__name__)


class DualAuthModelBackend(ModelBackend):
    """
    This is a ModelBacked that allows authentication with either a username or an email address.
    """
    def authenticate(self, request, username=None, password=None):
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
