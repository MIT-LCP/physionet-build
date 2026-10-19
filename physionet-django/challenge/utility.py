"""
Helpers for the challenge app.
"""
import logging

from django.conf import settings
from django.urls import NoReverseMatch, reverse

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
    try:
        url = reverse('challenge_detail', kwargs={
            'challenge_slug': challenge.slug,
        })
    except NoReverseMatch:
        url = ''

    for p in participants:
        create_notification(
            recipient=p.user,
            notification_type=NotificationType.CHALLENGE_PHASE_CHANGE,
            message=message[:500],
            url=url,
        )


def published_challenge_context(project, user):
    """
    Template context for the challenge content shown on a published
    project page. Returns an empty dict when the project has no challenge
    or challenges are disabled (the challenge URLs the templates link to
    are only registered when ENABLE_CHALLENGES is set).
    """
    if not settings.ENABLE_CHALLENGES:
        return {}
    challenge = getattr(project, 'challenge', None)
    if challenge is None:
        return {}

    from challenge.enums import ChallengePhase, DatasetType, SubmissionStatus
    from challenge.models import LeaderboardEntry

    leaderboard = LeaderboardEntry.objects.filter(
        challenge=challenge,
    ).select_related('user', 'team', 'submission').order_by('rank')
    show_test = challenge.phase == ChallengePhase.RESULTS

    return {
        'challenge': challenge,
        'challenge_participant_count': challenge.participants.filter(
            is_active=True).count(),
        'challenge_submission_count': challenge.submissions.filter(
            status=SubmissionStatus.COMPLETED).count(),
        'challenge_teams_count': challenge.teams.filter(
            is_active=True).count(),
        'challenge_rules': challenge.rules,
        'challenge_submission_spec': getattr(challenge, 'submission_spec', None),
        'challenge_leaderboard': leaderboard.filter(dataset=DatasetType.VAL),
        'challenge_leaderboard_test': (
            leaderboard.filter(dataset=DatasetType.TEST) if show_test else []
        ),
        'challenge_show_test_leaderboard': show_test,
    }
