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


@register.simple_tag(name='mail_credential_applicant', takes_context=True)
def mail_credential_applicant(context, a):
    """
    Prepare a template email to someone who has applied for credentialing.
    """
    return notification.mailto_process_credential_complete(context['request'],
                                                           a, comments=False)
