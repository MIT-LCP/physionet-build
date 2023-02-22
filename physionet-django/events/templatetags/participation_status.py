from django import template

from events.models import EventApplication

register = template.Library()


@register.filter(name='is_participant')
def is_participant(user, event):
    return event.participants.filter(user=user).exists()


@register.filter(name='is_on_waiting_list')
def is_on_waiting_list(user, event):
    return EventApplication.objects.filter(
        user=user,
        event=event,
        status=EventApplication.EventApplicationStatus.WAITLISTED
    ).exists()


@register.filter(name='has_access_to_event_dataset')
def has_access_to_event_dataset(user, dataset):
    return dataset.has_access(user)
