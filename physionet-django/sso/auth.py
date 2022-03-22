from django.contrib.auth import get_user_model

UserModel = get_user_model()


class RemoteUserBackend:
    """Django Authentication Backend that should be used for SSO.

    Instead of using login/password auth like the DualAuthModelBackend, this backend uses the sso_id field.

    The remote_user value should be taken from uwsgi headers that are set by the proxy server, after authentiating
    with Shibboleth or other SSO technology. IT SHOULD NOT BE SUPPLIED DIRECTLY BY THE USER.
    """

    def authenticate(self, request, remote_user=None):
        if not remote_user:
            return

        user = self._get_user_or_none(sso_id=remote_user)
        return user if self.user_can_authenticate(user) else None

    def get_user(self, user_id):
        user = self._get_user_or_none(pk=user_id)
        return user if self.user_can_authenticate(user) else None

    def user_can_authenticate(self, user):
        is_active = getattr(user, 'is_active', None)
        return is_active or is_active is None

    def _get_user_or_none(self, **kwargs):
        try:
            return UserModel.objects.get(**kwargs)
        except UserModel.DoesNotExist:
            return None
