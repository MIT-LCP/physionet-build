from enum import Enum


class LogCategory(Enum):
    ACCESS = 'Access'
    GCP = 'GCP'
    ENTITLEMENT_CHECK = 'Entitlement Check'

    @classmethod
    def choices(cls):
        return tuple((option.name, option.value) for option in cls)
