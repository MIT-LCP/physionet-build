import notification.utility as notification


def notify_host_cohosts_new_registration(request, registered_user, event):
    """
    Notify the host and cohosts of an event of a message.
    """

    notification.notify_event_participant_application(
        request=request,
        user=event.host,
        registered_user=registered_user,
        event=event
    )

    for participant in event.participants.all():
        if participant.is_cohost:
            notification.notify_event_participant_application(
                request=request,
                user=participant.user,
                registered_user=registered_user,
                event=event
            )
