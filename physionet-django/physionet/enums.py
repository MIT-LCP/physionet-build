from enum import Enum


class Page(Enum):
    ABOUT = 'Abount'
    SHARE = 'Share'

    @classmethod
    def choices(cls):
        return tuple((option.name, option.value) for option in cls)