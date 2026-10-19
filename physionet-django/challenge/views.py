from functools import wraps

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from challenge.enums import ChallengePhase
from challenge.models import Challenge, ChallengeParticipant


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

    open_phases = [
        ChallengePhase.REGISTRATION,
        ChallengePhase.UNOFFICIAL,
        ChallengePhase.OFFICIAL,
    ]
    completed_phases = [ChallengePhase.RESULTS, ChallengePhase.ARCHIVED]

    if filter_status == 'open':
        open_challenges = base_qs.filter(
            phase__in=open_phases,
        ).exclude(phase=ChallengePhase.REGISTRATION)
        completed_challenges = Challenge.objects.none()
    elif filter_status == 'upcoming':
        open_challenges = base_qs.filter(phase=ChallengePhase.REGISTRATION)
        completed_challenges = Challenge.objects.none()
    elif filter_status == 'completed':
        open_challenges = Challenge.objects.none()
        completed_challenges = base_qs.filter(phase__in=completed_phases)
    else:
        open_challenges = base_qs.filter(
            phase__in=open_phases,
        ).exclude(phase=ChallengePhase.REGISTRATION)
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
