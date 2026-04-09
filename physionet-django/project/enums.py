from enum import IntEnum


class AccessPolicy(IntEnum):
    OPEN = 0
    RESTRICTED = 1
    CREDENTIALED = 2
    CONTRIBUTOR_REVIEW = 3

    do_not_call_in_templates = True

    @classmethod
    def choices(cls, gte_value=0):
        return tuple(
            (option.value, option.name.replace("_", " ").title())
            for option in cls if option.value >= gte_value
        )
