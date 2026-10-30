import hashlib
import logging

from django.conf import settings
from django.contrib.auth.backends import ModelBackend, BaseBackend
from django.core.cache import cache

from physionet.utility import get_client_ip
from user.models import User

logger = logging.getLogger(__name__)


def _login_failure_counters(request, username):
    """
    Returns (cache key, limit) pairs counting failed logins for this client address
    and account, and for this client address across all accounts.
    """
    client = hashlib.sha256((get_client_ip(request) or '').encode()).hexdigest()
    account = hashlib.sha256(username.lower().encode()).hexdigest()
    return (
        (f'login-failures:account:{client}:{account}', settings.LOGIN_FAILURE_LIMIT),
        (f'login-failures:client:{client}', settings.LOGIN_FAILURE_CLIENT_LIMIT),
    )


def is_login_limited(request, username):
    """
    Returns True if this client has had too many recent failed logins, either for
    this account or overall.  Calls without a request are never limited.
    """
    if request is None or not username:
        return False
    return any((cache.get(key) or 0) >= limit
               for key, limit in _login_failure_counters(request, username))


def _record_login_failure(request, username):
    if request is None:
        return
    for key, _ in _login_failure_counters(request, username):
        # The window starts at the first failure and is not extended by later ones
        if not cache.add(key, 1, settings.LOGIN_FAILURE_WINDOW):
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, settings.LOGIN_FAILURE_WINDOW)


def _clear_login_failures(request, username):
    if request is None:
        return
    account_key, _ = _login_failure_counters(request, username)[0]
    caches['login_failures'].delete(account_key)


class DualAuthModelBackend(ModelBackend):
    """
    This is a ModelBacked that allows authentication with either a username or an email address.
    """
    def authenticate(self, request, username=None, password=None):
        # After implementation of OAuth2, (presumably) many crawlers started to attempt
        # authentication with tokens, causing server errors due to the comparison below.
        if username is None:
            return None
        if is_login_limited(request, username):
            logger.warning('Too many failed logins from {0}'.format(get_client_ip(request)))
            return None
        if '@' in username:
            kwargs = {'email': username.lower()}
        else:
            kwargs = {'username': username.lower()}
        try:
            user = User.objects.get(**kwargs)
            if user.check_password(password):
                _clear_login_failures(request, username)
                return user
        except User.DoesNotExist:
            logger.error('Unsuccessful authentication {0}'.format(username.lower()))
        _record_login_failure(request, username)
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
