from user.forms import RegistrationForm


class SSORegistrationForm(RegistrationForm):
    def __init__(self, *args, **kwargs):
        self.sso_id = kwargs.pop('sso_id', None)
        super().__init__(*args, **kwargs)

    def save(self):
        return super().save(sso_id=self.sso_id)
