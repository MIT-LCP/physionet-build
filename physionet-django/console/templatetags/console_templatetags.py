from django import template

import notification.utility as notification

register = template.Library()


@register.filter(name='task_count_badge')
def task_count_badge(item):
    """
    Return a red or green badge indicating the number of elements in
    an iterable
    """
    if item:
        context_class = 'danger'
    else:
        context_class = 'success'
    return '<span class="badge badge-pill badge-{}">{}</span>'.format(
        context_class, len(item))


@register.filter(name='get_verified_emails')
def get_verified_emails(user):
    """
    Get a list of non-primary, verified email addresses.
    """
    return user.get_emails(is_verified=True, include_primary=False)


@register.filter(name='smooth_timedelta')
def smooth_timedelta(timedelta):
    seconds = timedelta.total_seconds()

    hours = seconds // 3600 if seconds >= 3600 else 0
    seconds -= hours * 3600

    minutes = seconds // 60 if seconds >= 60 else 0
    seconds -= minutes * 60

    return f'{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}'
