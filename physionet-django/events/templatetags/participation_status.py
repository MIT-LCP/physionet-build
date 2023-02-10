from django import template

register = template.Library()


@register.filter(name='is_participant')
def is_participant(user, event):
    return event.participants.filter(user=user).exists()
