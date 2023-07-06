from django.utils import timezone


def has_event_access(user, event):
    """
    Checks if the user has access to the event
    """
    return event.host == user or event.participants.filter(user=user).exists()


def has_access_to_event_dataset(user, event_dataset):
    """
    Checks if the user has access to the event dataset
    """
    if not has_event_access(user, event_dataset.event):
        return False

    if not event_dataset.is_active:
        return False

    if timezone.now().date() > event_dataset.event.end_date:
        return False

    return True
