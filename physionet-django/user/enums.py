from enum import IntEnum


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


class EventType(IntEnum):
    COURSE = 0
    DATATHON = 1
    CONFERENCE = 2
    WORKSHOP = 3
    SYMPOSIUM = 4

    @classmethod
    def choices(cls):
        return tuple((option.value, option.name) for option in cls)
