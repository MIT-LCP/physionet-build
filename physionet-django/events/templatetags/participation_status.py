from django import template

from events.models import EventApplication
from project.authorization.events import has_access_to_event_dataset as has_access_to_event_dataset_func

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
    return has_access_to_event_dataset_func(user, dataset)


@register.filter(name='get_inactive_applications')
def get_inactive_applications(event):
    return event.applications.filter(
        status__in=[
            EventApplication.EventApplicationStatus.NOT_APPROVED,
            EventApplication.EventApplicationStatus.WITHDRAWN
        ]
    )


@register.filter(name='get_pending_applications')
def get_pending_applications(event):
    return event.applications.filter(
        status__in=[EventApplication.EventApplicationStatus.WAITLISTED]
    )


@register.filter(name='get_withdrawn_applications')
def get_withdrawn_applications(event):
    return event.applications.filter(
        status__in=[EventApplication.EventApplicationStatus.WITHDRAWN]
    )


@register.filter(name='get_rejected_applications')
def get_rejected_applications(event):
    return event.applications.filter(
        status__in=[EventApplication.EventApplicationStatus.NOT_APPROVED]
    )
