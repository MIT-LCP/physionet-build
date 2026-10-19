"""
Notification helpers for the challenge app.
"""
import logging

from django.urls import reverse

from notification.models import NotificationType
from notification.utility import create_notification

logger = logging.getLogger(__name__)


def notify_phase_change(challenge, old_phase, new_phase):
    """Notify all participants of a challenge phase change."""
    participants = challenge.participants.filter(
        is_active=True,
    ).select_related('user')

    message = (
        f'Challenge "{challenge.slug}" has moved from '
        f'{old_phase} to {new_phase}.'
    )
    url = reverse('challenge_detail', kwargs={
        'challenge_slug': challenge.slug,
    })

    for p in participants:
        create_notification(
            recipient=p.user,
            notification_type=NotificationType.CHALLENGE_PHASE_CHANGE,
            message=message[:500],
            url=url,
        )
