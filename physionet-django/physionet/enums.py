from enum import Enum


class Page(Enum):
    ABOUT = 'about'
    SHARE = 'share'

    @classmethod
    def choices(cls):
        return tuple((option.name, option.value) for option in cls)