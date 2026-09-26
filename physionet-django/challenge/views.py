import hashlib
import logging
import os
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from challenge.enums import ChallengePhase, DatasetType, SubmissionStatus
from challenge.forms import (
    ChallengeManageForm,
    CodeSubmissionForm,
    TeamCreateForm,
    TeamInviteForm,
    TeamInvitationResponseForm,
)
from challenge.models import (
    Challenge,
    ChallengeParticipant,
    LeaderboardEntry,
    Submission,
    Team,
    TeamInvitation,
)

logger = logging.getLogger(__name__)


# ── Auth decorator ──────────────────────────────────────────────────

def challenge_auth(require_participant=False, require_organizer=False):
    """
    Authorization decorator for challenge views.

    Resolves ``challenge_slug`` from kwargs, loads the Challenge and
    (if the user is authenticated) the ChallengeParticipant, then
    injects both into view kwargs.

    Flags:
    - require_participant: user must be a registered participant.
    - require_organizer: user must be the challenge organizer or have
      the ``manage_challenge`` permission.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            challenge = get_object_or_404(
                Challenge, slug=kwargs.pop('challenge_slug'),
            )
            participant = None
            if request.user.is_authenticated:
                participant = ChallengeParticipant.objects.filter(
                    user=request.user, challenge=challenge, is_active=True,
                ).first()

            if require_organizer:
                is_organizer = (
                    request.user == challenge.organizer
                    or request.user.has_perm('challenge.manage_challenge')
                )
                if not is_organizer:
                    raise PermissionDenied
            if require_participant and not participant:
                raise PermissionDenied

            kwargs['challenge'] = challenge
            kwargs['participant'] = participant
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ── Public views ────────────────────────────────────────────────────

def challenge_list(request):
    """List challenges with optional status filtering."""
    filter_status = request.GET.get('status', '')

    base_qs = Challenge.objects.filter(
        is_active=True,
    ).select_related(
        'published_project', 'organizer',
    ).annotate(
        participant_count=Count('participants', filter=Q(participants__is_active=True)),
    ).order_by('-start_datetime')

    open_phases = [ChallengePhase.REGISTRATION, ChallengePhase.UNOFFICIAL, ChallengePhase.OFFICIAL]
    completed_phases = [ChallengePhase.RESULTS, ChallengePhase.ARCHIVED]

    if filter_status == 'open':
        open_challenges = base_qs.filter(phase__in=open_phases).exclude(phase=ChallengePhase.REGISTRATION)
        completed_challenges = Challenge.objects.none()
    elif filter_status == 'upcoming':
        open_challenges = base_qs.filter(phase=ChallengePhase.REGISTRATION)
        completed_challenges = Challenge.objects.none()
    elif filter_status == 'completed':
        open_challenges = Challenge.objects.none()
        completed_challenges = base_qs.filter(phase__in=completed_phases)
    else:
        open_challenges = base_qs.filter(phase__in=open_phases).exclude(phase=ChallengePhase.REGISTRATION)
        completed_challenges = base_qs.filter(phase__in=completed_phases)

    return render(request, 'challenge/challenge_list.html', {
        'open_challenges': open_challenges,
        'completed_challenges': completed_challenges,
        'filter_status': filter_status,
    })


@challenge_auth()
def challenge_detail(request, challenge, participant, **kwargs):
    """Redirect to the published project page."""
    return redirect('published_project',
                    challenge.published_project.slug,
                    challenge.published_project.version)


@challenge_auth()
def challenge_rules(request, challenge, participant, **kwargs):
    """Redirect to the published project page rules tab."""
    url = reverse('published_project', args=[
        challenge.published_project.slug,
        challenge.published_project.version,
    ])
    return redirect(url + '#rules')


@challenge_auth()
def challenge_leaderboard(request, challenge, participant, **kwargs):
    """Redirect to the published project page leaderboard tab."""
    url = reverse('published_project', args=[
        challenge.published_project.slug,
        challenge.published_project.version,
    ])
    return redirect(url + '#leaderboard')


# ── Participant views ───────────────────────────────────────────────

@login_required
@challenge_auth()
def challenge_register(request, challenge, participant, **kwargs):
    """Register for a challenge."""
    if participant:
        messages.info(request, 'You are already registered for this challenge.')
        return redirect('published_project',
                        challenge.published_project.slug,
                        challenge.published_project.version)

    if not challenge.is_registration_open:
        messages.error(request, 'Registration is not open for this challenge.')
        return redirect('published_project',
                        challenge.published_project.slug,
                        challenge.published_project.version)

    if request.method == 'POST':
        ChallengeParticipant.objects.create(
            user=request.user, challenge=challenge,
        )
        messages.success(request, 'You have successfully registered.')
        return redirect('published_project',
                        challenge.published_project.slug,
                        challenge.published_project.version)

    return render(request, 'challenge/challenge_register.html', {
        'challenge': challenge,
    })


@login_required
@challenge_auth(require_participant=True)
def challenge_submit(request, challenge, participant, **kwargs):
    """Submit code to the challenge."""
    if not challenge.is_accepting_submissions:
        messages.error(request, 'This challenge is not accepting submissions.')
        return redirect('published_project',
                        challenge.published_project.slug,
                        challenge.published_project.version)

    # Check submission limits
    today_count = Submission.objects.filter(
        challenge=challenge,
        submitted_by=request.user,
        created_datetime__date=timezone.now().date(),
    ).count()
    if today_count >= challenge.max_submissions_per_day:
        messages.error(request, 'Daily submission limit reached.')
        url = reverse('published_project', args=[
            challenge.published_project.slug,
            challenge.published_project.version,
        ])
        return redirect(url + '#submit')

    total_count = Submission.objects.filter(
        challenge=challenge, submitted_by=request.user,
    ).count()
    if total_count >= challenge.max_total_submissions:
        messages.error(request, 'Total submission limit reached.')
        url = reverse('published_project', args=[
            challenge.published_project.slug,
            challenge.published_project.version,
        ])
        return redirect(url + '#submit')

    form = CodeSubmissionForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        archive = form.cleaned_data['code_archive']

        # Compute SHA-256
        sha256 = hashlib.sha256()
        for chunk in archive.chunks():
            sha256.update(chunk)
        archive_hash = sha256.hexdigest()

        # Upload to GCS staging bucket
        gcs_uri = _upload_code_archive(challenge, request.user, archive)

        submission = Submission.objects.create(
            challenge=challenge,
            submitted_by=request.user,
            team=participant.team,
            code_archive_gcs_uri=gcs_uri,
            code_archive_sha256=archive_hash,
            description=form.cleaned_data.get('description', ''),
        )

        # Enqueue background task
        from challenge.tasks import process_submission
        process_submission(submission.pk)

        messages.success(request, 'Submission uploaded and queued.')
        return redirect('challenge_submission_detail',
                        challenge_slug=challenge.slug,
                        submission_id=submission.pk)

    return render(request, 'challenge/challenge_submit.html', {
        'challenge': challenge,
        'participant': participant,
        'form': form,
        'today_count': today_count,
        'total_count': total_count,
    })


@login_required
@challenge_auth(require_participant=True)
def challenge_my_submissions(request, challenge, participant, **kwargs):
    """Redirect to the published project page submit tab."""
    url = reverse('published_project', args=[
        challenge.published_project.slug,
        challenge.published_project.version,
    ])
    return redirect(url + '#submit')


@login_required
@challenge_auth(require_participant=True)
def challenge_submission_detail(request, challenge, participant,
                                submission_id, **kwargs):
    """View a single submission's details."""
    submission = get_object_or_404(
        Submission, pk=submission_id, challenge=challenge,
    )

    # Only the submitter, their team members, or the organizer can view
    if (submission.submitted_by != request.user
            and request.user != challenge.organizer
            and not request.user.has_perm('challenge.manage_challenge')):
        if submission.team and participant.team != submission.team:
            raise PermissionDenied

    scores = submission.scores.all()
    return render(request, 'challenge/challenge_submission_detail.html', {
        'challenge': challenge,
        'participant': participant,
        'submission': submission,
        'scores': scores,
    })


# ── Team views ──────────────────────────────────────────────────────

@login_required
@challenge_auth(require_participant=True)
def challenge_team(request, challenge, participant, **kwargs):
    """View current team details."""
    if not challenge.teams_enabled:
        raise PermissionDenied

    team = participant.team
    members = []
    invitations = []
    if team:
        members = ChallengeParticipant.objects.filter(
            team=team, is_active=True,
        ).select_related('user')
        invitations = TeamInvitation.objects.filter(
            team=team, is_active=True, response__isnull=True,
        )

    return render(request, 'challenge/team_manage.html', {
        'challenge': challenge,
        'participant': participant,
        'team': team,
        'members': members,
        'invitations': invitations,
    })


@login_required
@challenge_auth(require_participant=True)
def challenge_team_create(request, challenge, participant, **kwargs):
    """Create a new team."""
    if not challenge.teams_enabled:
        raise PermissionDenied
    if participant.team:
        messages.error(request, 'You are already on a team.')
        return redirect('challenge_team', challenge_slug=challenge.slug)

    form = TeamCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            team = form.save(commit=False)
            team.challenge = challenge
            team.save()
            participant.team = team
            participant.is_team_captain = True
            participant.save()
        messages.success(request, f'Team "{team.name}" created.')
        return redirect('challenge_team', challenge_slug=challenge.slug)

    return render(request, 'challenge/team_create.html', {
        'challenge': challenge,
        'participant': participant,
        'form': form,
    })


@login_required
@challenge_auth(require_participant=True)
def challenge_team_invite(request, challenge, participant, **kwargs):
    """Invite someone to your team."""
    if not challenge.teams_enabled or not participant.team:
        raise PermissionDenied
    if not participant.is_team_captain:
        messages.error(request, 'Only the team captain can send invitations.')
        return redirect('challenge_team', challenge_slug=challenge.slug)

    form = TeamInviteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        TeamInvitation.objects.create(
            team=participant.team,
            email=email,
            invited_by=request.user,
        )
        # Send notification
        from challenge.utility import team_invitation_notify
        team_invitation_notify(request, participant.team, email)

        messages.success(request, f'Invitation sent to {email}.')
        return redirect('challenge_team', challenge_slug=challenge.slug)

    return render(request, 'challenge/team_invite.html', {
        'challenge': challenge,
        'participant': participant,
        'form': form,
    })


@login_required
@challenge_auth(require_participant=True)
def challenge_team_invitation_respond(request, challenge, participant,
                                      invitation_id, **kwargs):
    """Respond to a team invitation."""
    invitation = get_object_or_404(
        TeamInvitation, pk=invitation_id, is_active=True,
        response__isnull=True,
    )
    # Verify the invitation is for this user
    if invitation.email not in request.user.get_emails():
        raise PermissionDenied

    form = TeamInvitationResponseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        accepted = form.cleaned_data['accept']
        with transaction.atomic():
            invitation.response = accepted
            invitation.response_datetime = timezone.now()
            invitation.is_active = False
            invitation.save()

            if accepted:
                participant.team = invitation.team
                participant.save()

        action = 'accepted' if accepted else 'declined'
        messages.success(request, f'You have {action} the invitation.')
        return redirect('challenge_team', challenge_slug=challenge.slug)

    return render(request, 'challenge/team_invitation_respond.html', {
        'challenge': challenge,
        'participant': participant,
        'invitation': invitation,
        'form': form,
    })


@login_required
@challenge_auth(require_participant=True)
def challenge_submission_select(request, challenge, participant,
                                submission_id, **kwargs):
    """Select a submission as the active leaderboard entry."""
    if request.method != 'POST':
        raise PermissionDenied

    submission = get_object_or_404(
        Submission, pk=submission_id, challenge=challenge,
        status=SubmissionStatus.COMPLETED,
    )

    # Verify the user owns the submission (or is team captain)
    if submission.team:
        if not participant.team or participant.team != submission.team:
            raise PermissionDenied
        if not participant.is_team_captain:
            raise PermissionDenied
    else:
        if submission.submitted_by != request.user:
            raise PermissionDenied

    # Get the primary score for this submission
    spec = challenge.submission_spec
    primary_score = submission.scores.filter(
        metric_name=spec.primary_metric_name,
        dataset=DatasetType.VAL,
    ).first()

    if not primary_score:
        messages.error(request, 'This submission has no scores to display on the leaderboard.')
        url = reverse('published_project', args=[
            challenge.published_project.slug,
            challenge.published_project.version,
        ])
        return redirect(url + '#submit')

    all_scores = {
        s.metric_name: s.value
        for s in submission.scores.filter(dataset=DatasetType.VAL)
    }

    with transaction.atomic():
        # Clear is_selected on all of this participant's/team's submissions
        if submission.team:
            Submission.objects.filter(
                challenge=challenge, team=submission.team, is_selected=True,
            ).update(is_selected=False)
        else:
            Submission.objects.filter(
                challenge=challenge, submitted_by=request.user,
                team__isnull=True, is_selected=True,
            ).update(is_selected=False)

        # Set is_selected on the chosen submission
        submission.is_selected = True
        submission.save(update_fields=['is_selected'])

        # Update the leaderboard entry
        lookup = {
            'challenge': challenge,
            'dataset': DatasetType.VAL,
        }
        if submission.team:
            lookup['team'] = submission.team
            lookup['user'] = None
        else:
            lookup['user'] = submission.submitted_by
            lookup['team'] = None

        entry, created = LeaderboardEntry.objects.get_or_create(
            defaults={
                'submission': submission,
                'primary_score': primary_score.value,
                'all_scores': all_scores,
            },
            **lookup,
        )
        if not created:
            entry.submission = submission
            entry.primary_score = primary_score.value
            entry.all_scores = all_scores
            entry.save(update_fields=[
                'submission', 'primary_score', 'all_scores',
            ])

    # Recompute ranks
    from challenge.tasks import recompute_leaderboard
    recompute_leaderboard(challenge.pk)

    messages.success(request, 'Submission selected for the leaderboard.')
    url = reverse('published_project', args=[
        challenge.published_project.slug,
        challenge.published_project.version,
    ])
    return redirect(url + '#submit')


@login_required
@challenge_auth(require_participant=True)
def challenge_submission_statuses(request, challenge, participant, **kwargs):
    """Return JSON with current statuses of the user's submissions."""
    submissions = Submission.objects.filter(
        challenge=challenge,
        submitted_by=request.user,
    ).values_list('pk', 'status')

    statuses = {
        str(pk): {
            'status': status,
            'display': SubmissionStatus(status).label,
        }
        for pk, status in submissions
    }
    return JsonResponse({'statuses': statuses})


# ── Organizer / management views ────────────────────────────────────

@login_required
@challenge_auth(require_organizer=True)
def challenge_manage(request, challenge, participant, **kwargs):
    """Organizer dashboard with statistics and settings."""
    stats = {
        'participants': challenge.participants.filter(is_active=True).count(),
        'teams': challenge.teams.filter(is_active=True).count(),
        'total_submissions': challenge.submissions.count(),
        'completed_submissions': challenge.submissions.filter(
            status=SubmissionStatus.COMPLETED,
        ).count(),
        'pending_submissions': challenge.submissions.filter(
            status__in=[
                SubmissionStatus.PENDING,
                SubmissionStatus.BUILDING,
                SubmissionStatus.RUNNING,
                SubmissionStatus.SCORING,
            ],
        ).count(),
    }

    form = ChallengeManageForm(
        request.POST or None, instance=challenge,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Challenge settings updated.')
        return redirect('challenge_manage', challenge_slug=challenge.slug)

    spec = getattr(challenge, 'submission_spec', None)

    return render(request, 'challenge/challenge_manage.html', {
        'challenge': challenge,
        'participant': participant,
        'stats': stats,
        'form': form,
        'spec': spec,
    })


@login_required
@challenge_auth(require_organizer=True)
def challenge_manage_submissions(request, challenge, participant, **kwargs):
    """View all submissions for the challenge."""
    submissions = challenge.submissions.select_related(
        'submitted_by', 'team',
    ).order_by('-created_datetime')

    return render(request, 'challenge/challenge_manage_submissions.html', {
        'challenge': challenge,
        'participant': participant,
        'submissions': submissions,
    })


@login_required
@challenge_auth(require_organizer=True)
def challenge_download_evaluation_script(request, challenge, participant, **kwargs):
    """Download the evaluation script from GCS."""
    spec = getattr(challenge, 'submission_spec', None)
    if not spec or not spec.evaluation_script_gcs_uri:
        raise Http404

    from physionet.gcp import ObjectPath
    obj = ObjectPath(spec.evaluation_script_gcs_uri)
    blob = obj.bucket().blob(obj.key())
    content = blob.download_as_bytes()
    filename = os.path.basename(obj.key())

    response = HttpResponse(content, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── Helpers ─────────────────────────────────────────────────────────

def _upload_code_archive(challenge, user, archive_file):
    """Upload a code archive to GCS and return the URI."""
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    bucket = getattr(settings, 'CHALLENGE_STAGING_BUCKET', '')
    key = f'challenges/{challenge.slug}/submissions/{user.pk}/{timestamp}/{archive_file.name}'
    gcs_uri = f'{bucket}/{key}'

    try:
        from physionet.gcp import ObjectPath
        obj = ObjectPath(gcs_uri)
        blob = obj.bucket().blob(obj.key())
        blob.upload_from_file(archive_file, rewind=True)
    except Exception:
        logger.exception('Failed to upload code archive to GCS')
        raise

    return gcs_uri


