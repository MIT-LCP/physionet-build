"""
Helpers for the challenge app.
"""
import logging

from django.conf import settings
from django.db.models import Q
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


def pending_team_invitations(challenge, user):
    """
    Unanswered invitations to teams in this challenge that were sent to
    any of the user's verified email addresses (case-insensitive).
    """
    from challenge.models import TeamInvitation

    emails = user.get_emails()
    if not emails:
        return TeamInvitation.objects.none()
    email_match = Q()
    for email in emails:
        email_match |= Q(email__iexact=email)
    return TeamInvitation.objects.filter(
        email_match,
        team__challenge=challenge,
        team__is_active=True,
        is_active=True,
        response__isnull=True,
    ).select_related('team', 'invited_by')


def team_invitation_notify(invitation):
    """Notify a user that they have been invited to a challenge team."""
    from user.models import AssociatedEmail
    try:
        assoc = AssociatedEmail.objects.get(
            email__iexact=invitation.email, is_verified=True,
        )
    except AssociatedEmail.DoesNotExist:
        return

    team = invitation.team
    challenge = team.challenge
    try:
        url = reverse('challenge_team_invitation_respond', kwargs={
            'challenge_slug': challenge.slug,
            'invitation_id': invitation.pk,
        })
    except NoReverseMatch:
        url = ''

    message = (
        f'You have been invited to join team "{team.name}" '
        f'in the challenge "{challenge.slug}".'
    )
    create_notification(
        recipient=assoc.user,
        notification_type=NotificationType.CHALLENGE_TEAM_INVITATION,
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

    context = {
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
    if user.is_authenticated:
        context.update(_participant_context(challenge, user))
    return context


def _participant_context(challenge, user):
    """Context for the Submit and Team tabs (registered participants only)."""
    from challenge.models import ChallengeParticipant, Submission, TeamInvitation

    participant = ChallengeParticipant.objects.filter(
        user=user, challenge=challenge, is_active=True,
    ).select_related('team').first()
    if participant is None:
        return {}

    context = {
        'challenge_participant': participant,
        'challenge_my_submissions': Submission.objects.filter(
            challenge=challenge, submitted_by=user,
        ).order_by('-created_datetime'),
        'challenge_my_invitations': pending_team_invitations(challenge, user),
    }
    team = participant.team
    if team:
        context['challenge_team'] = team
        context['challenge_team_members'] = ChallengeParticipant.objects.filter(
            team=team, is_active=True,
        ).select_related('user')
        if participant.is_team_captain:
            context['challenge_team_invitations'] = TeamInvitation.objects.filter(
                team=team, is_active=True, response__isnull=True,
            )
    return context
