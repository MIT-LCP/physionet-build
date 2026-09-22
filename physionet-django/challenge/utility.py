"""
Notification helpers for the challenge app.
"""
import logging

from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.template import loader
from django.urls import reverse

from notification.models import NotificationType
from notification.utility import create_notification, get_url_prefix

logger = logging.getLogger(__name__)


def notify_submission_complete(submission):
    """Notify the submitter that their submission scored successfully."""
    challenge = submission.challenge
    recipient = submission.submitted_by
    scores = submission.scores.all()

    score_summary = ', '.join(
        f'{s.metric_name}: {s.value}' for s in scores
    )
    message = (
        f'Your submission to "{challenge.slug}" has been scored. '
        f'{score_summary}'
    )
    url = reverse('challenge_submission_detail', kwargs={
        'challenge_slug': challenge.slug,
        'submission_id': submission.pk,
    })

    create_notification(
        recipient=recipient,
        notification_type=NotificationType.CHALLENGE_SUBMISSION_COMPLETE,
        message=message[:500],
        url=url,
    )


def notify_submission_failed(submission):
    """Notify the submitter that their submission failed."""
    challenge = submission.challenge
    recipient = submission.submitted_by

    message = (
        f'Your submission to "{challenge.slug}" failed: '
        f'{submission.error_message[:200]}'
    )
    url = reverse('challenge_submission_detail', kwargs={
        'challenge_slug': challenge.slug,
        'submission_id': submission.pk,
    })

    create_notification(
        recipient=recipient,
        notification_type=NotificationType.CHALLENGE_SUBMISSION_FAILED,
        message=message[:500],
        url=url,
    )


def team_invitation_notify(request, team, target_email):
    """Notify someone when they are invited to join a challenge team."""
    challenge = team.challenge
    inviter = request.user

    subject = f'Invitation to join team "{team.name}" for challenge: {challenge.slug}'
    email_context = {
        'inviter_name': inviter.get_full_name(),
        'team': team,
        'challenge': challenge,
        'domain': get_current_site(request),
        'url_prefix': get_url_prefix(request),
        'signature': settings.EMAIL_SIGNATURE,
        'SITE_NAME': settings.SITE_NAME,
    }
    body = loader.render_to_string(
        'challenge/email/team_invitation.html', email_context,
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
              [target_email], fail_silently=False)


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
