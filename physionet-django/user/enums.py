from enum import IntEnum

from django.db import models


class TrainingStatus(IntEnum):
    REVIEW = 0
    WITHDRAWN = 1
    REJECTED = 2
    ACCEPTED = 3

    @classmethod
    def choices(cls):
        return tuple((option.value, option.name) for option in cls)


class RequiredField(IntEnum):
    DOCUMENT = 0
    URL = 1

    @classmethod
    def choices(cls):
        return tuple((option.value, option.name) for option in cls)
