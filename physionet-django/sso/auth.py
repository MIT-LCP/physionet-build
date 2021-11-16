from django.contrib.auth import get_user_model

UserModel = get_user_model()


class RemoteUserBackend:
    def authenticate(self, request, remote_user=None):
        if not remote_user:
            return

        user = None
        print("Authenticating as:", remote_user)
        try:
            user = UserModel.objects.get(shibboleth_id=remote_user)
            print("User found")
        except UserModel.DoesNotExist:
            print("User not found")
            pass

        return user if self.user_can_authenticate(user) else None

    def get_user(self, user_id):
        print("Getting user with id", user_id)
        try:
            user = UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None

    def user_can_authenticate(self, user):
        is_active = getattr(user, 'is_active', None)
        return is_active or is_active is None
