from enum import Enum

from django.conf import settings


class Page(Enum):
    ABOUT = 'about'
    SHARE = 'share'
    SSO_LOGIN = 'sso login'

    @classmethod
    def choices(cls):
        return tuple((option.name, option.value) for option in cls)

    @classmethod
    def available_choices(cls):
        all_choices = cls.choices()
        if settings.ENABLE_SSO:
            return all_choices
        return tuple(choice for choice in all_choices if choice[0] != cls.SSO_LOGIN.name)
