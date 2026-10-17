"""
Background tasks for challenge submission processing and leaderboard updates.
"""
import logging

from background_task import background
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from challenge.enums import DatasetType, MetricSort, SubmissionStatus
from challenge.models import (
    Challenge,
    LeaderboardEntry,
    Score,
    Submission,
)
from console.tasks import associated_task

logger = logging.getLogger(__name__)


@associated_task(Submission, 'submission_id')
@background()
def process_submission(submission_id):
    """
    Main submission processing pipeline:
    1. Build - verify code archive
    2. Run - execute in Cloud Run Job
    3. Score - extract and save results
    4. Update leaderboard
    """
    from challenge.services import get_orchestrator
    from challenge.utility import (
        notify_submission_complete,
        notify_submission_failed,
    )

    try:
        submission = Submission.objects.select_related(
            'challenge__submission_spec',
        ).get(pk=submission_id)
    except Submission.DoesNotExist:
        logger.error('Submission %s not found', submission_id)
        return

    orchestrator = get_orchestrator(submission)

    try:
        # Build phase
        submission.status = SubmissionStatus.BUILDING
        submission.save(update_fields=['status'])
        orchestrator.build()

        # Run phase
        submission.status = SubmissionStatus.RUNNING
        submission.save(update_fields=['status'])
        orchestrator.run()

        # Poll for completion
        success = orchestrator.poll()
        if not success:
            submission.status = SubmissionStatus.FAILED
            submission.completed_datetime = timezone.now()
            submission.save(update_fields=['status', 'completed_datetime'])
            notify_submission_failed(submission)
            return

        # Scoring phase
        submission.status = SubmissionStatus.SCORING
        submission.save(update_fields=['status'])
        scores_data = orchestrator.extract_scores()

        # Save scores
        _save_scores(submission, scores_data)

        # Update leaderboard
        _update_leaderboard_entry(submission)

        # Mark completed
        submission.status = SubmissionStatus.COMPLETED
        submission.completed_datetime = timezone.now()
        submission.save(update_fields=['status', 'completed_datetime'])

        notify_submission_complete(submission)

    except Exception as exc:
        logger.exception('Submission %s failed', submission_id)
        submission.status = SubmissionStatus.FAILED
        submission.error_message = str(exc)[:2000]
        submission.completed_datetime = timezone.now()
        submission.save(update_fields=[
            'status', 'error_message', 'completed_datetime',
        ])
        notify_submission_failed(submission)

    finally:
        try:
            orchestrator.cleanup()
        except Exception:
            logger.exception('Cleanup failed for submission %s', submission_id)


@associated_task(Challenge, 'challenge_id', read_only=True)
@background()
def recompute_leaderboard(challenge_id):
    """Recalculate all ranks for a challenge."""
    try:
        challenge = Challenge.objects.get(pk=challenge_id)
    except Challenge.DoesNotExist:
        logger.error('Challenge %s not found', challenge_id)
        return

    spec = challenge.submission_spec
    sort_ascending = spec.primary_metric_sort == MetricSort.ASC

    for dataset in [DatasetType.VAL, DatasetType.TEST]:
        entries = LeaderboardEntry.objects.filter(
            challenge=challenge, dataset=dataset,
        ).order_by('primary_score' if sort_ascending else '-primary_score')

        for rank, entry in enumerate(entries, start=1):
            if entry.rank != rank:
                entry.rank = rank
                entry.save(update_fields=['rank'])


@associated_task(Challenge, 'challenge_id')
@background()
def transition_challenge_phase(challenge_id, target_phase):
    """Transition a challenge to a new phase and notify participants."""
    from challenge.utility import notify_phase_change

    try:
        challenge = Challenge.objects.get(pk=challenge_id)
    except Challenge.DoesNotExist:
        logger.error('Challenge %s not found', challenge_id)
        return

    old_phase = challenge.phase
    challenge.phase = target_phase
    challenge.save(update_fields=['phase'])

    notify_phase_change(challenge, old_phase, target_phase)
    logger.info('Challenge %s transitioned from %s to %s',
                challenge.slug, old_phase, target_phase)


def _save_scores(submission, scores_data, dataset=DatasetType.VAL):
    """Parse and save Score objects from the scoring output."""
    score_objects = []
    for metric_name, value in scores_data.items():
        score_objects.append(Score(
            submission=submission,
            metric_name=metric_name,
            value=float(value),
            dataset=dataset,
        ))
    Score.objects.bulk_create(score_objects)


def _update_leaderboard_entry(submission, dataset=DatasetType.VAL):
    """
    Update the leaderboard entry for this submission's participant/team.
    If this submission is better than their current entry, replace it.
    """
    challenge = submission.challenge
    spec = challenge.submission_spec
    sort_ascending = spec.primary_metric_sort == MetricSort.ASC

    primary_score = submission.scores.filter(
        metric_name=spec.primary_metric_name,
        dataset=dataset,
    ).first()

    if not primary_score:
        return

    all_scores = {
        s.metric_name: s.value
        for s in submission.scores.filter(dataset=dataset)
    }

    lookup = {
        'challenge': challenge,
        'dataset': dataset,
    }
    if submission.team:
        lookup['team'] = submission.team
        lookup['user'] = None
    else:
        lookup['user'] = submission.submitted_by
        lookup['team'] = None

    with transaction.atomic():
        entry, created = LeaderboardEntry.objects.get_or_create(
            defaults={
                'submission': submission,
                'primary_score': primary_score.value,
                'all_scores': all_scores,
            },
            **lookup,
        )

        if not created:
            # If the participant/team has manually selected a submission,
            # skip automatic replacement — their choice takes precedence.
            has_manual_selection = Submission.objects.filter(
                challenge=challenge,
                is_selected=True,
                status=SubmissionStatus.COMPLETED,
                **({'team': submission.team} if submission.team
                   else {'submitted_by': submission.submitted_by, 'team__isnull': True}),
            ).exists()

            if not has_manual_selection:
                # Check if new score is better
                is_better = (
                    (sort_ascending and primary_score.value < entry.primary_score)
                    or (not sort_ascending and primary_score.value > entry.primary_score)
                )
                if is_better:
                    entry.submission = submission
                    entry.primary_score = primary_score.value
                    entry.all_scores = all_scores
                    entry.save(update_fields=[
                        'submission', 'primary_score', 'all_scores',
                    ])

    # Recompute ranks
    recompute_leaderboard(challenge.pk)


def _advance_top_submissions(challenge):
    """
    Select the top N submissions per participant/team and enqueue
    them for test scoring. Called when transitioning to OFFICIAL phase.
    """
    spec = challenge.submission_spec
    sort_ascending = spec.primary_metric_sort == MetricSort.ASC
    n = challenge.max_submissions_to_advance

    completed_submissions = Submission.objects.filter(
        challenge=challenge,
        status=SubmissionStatus.COMPLETED,
    )

    if challenge.teams_enabled:
        # Group by team
        team_ids = completed_submissions.exclude(
            team__isnull=True,
        ).values_list('team_id', flat=True).distinct()

        for team_id in team_ids:
            team_subs = completed_submissions.filter(team_id=team_id)
            _select_top_n(team_subs, spec, n, sort_ascending)
    else:
        # Group by user
        user_ids = completed_submissions.values_list(
            'submitted_by_id', flat=True,
        ).distinct()

        for user_id in user_ids:
            user_subs = completed_submissions.filter(submitted_by_id=user_id)
            _select_top_n(user_subs, spec, n, sort_ascending)


def _select_top_n(submissions_qs, spec, n, sort_ascending):
    """
    From the given submissions queryset, find the top N by primary metric
    on VAL dataset and enqueue them for test scoring.
    """
    order_field = 'value' if sort_ascending else '-value'

    top_scores = Score.objects.filter(
        submission__in=submissions_qs,
        metric_name=spec.primary_metric_name,
        dataset=DatasetType.VAL,
    ).order_by(order_field)[:n]

    submission_ids = list(top_scores.values_list('submission_id', flat=True))

    Submission.objects.filter(pk__in=submission_ids).update(
        advanced_to_official=True,
    )

    for sub_id in submission_ids:
        process_test_scoring(sub_id)


@associated_task(Submission, 'submission_id')
@background()
def process_test_scoring(submission_id):
    """
    Re-evaluate a submission against the test dataset.
    Saves Score objects with dataset=TEST and creates/updates
    LeaderboardEntry with dataset=TEST.
    """
    from challenge.services import get_orchestrator

    try:
        submission = Submission.objects.select_related(
            'challenge__submission_spec',
        ).get(pk=submission_id)
    except Submission.DoesNotExist:
        logger.error('Submission %s not found for test scoring', submission_id)
        return

    # Guard against duplicate runs
    if submission.scores.filter(dataset=DatasetType.TEST).exists():
        logger.info(
            'Submission %s already has TEST scores, skipping',
            submission_id,
        )
        return

    orchestrator = get_orchestrator(submission)

    try:
        # Build phase
        orchestrator.build()

        # Run phase with test dataset
        orchestrator.run(dataset=DatasetType.TEST)

        # Poll for completion
        success = orchestrator.poll()
        if not success:
            logger.error(
                'Test scoring failed for submission %s', submission_id,
            )
            return

        # Extract and save test scores
        scores_data = orchestrator.extract_scores()
        _save_scores(submission, scores_data, dataset=DatasetType.TEST)
        _update_leaderboard_entry(submission, dataset=DatasetType.TEST)

        logger.info(
            'Test scoring completed for submission %s', submission_id,
        )

    except FileNotFoundError:
        logger.warning(
            'Code archive not found for submission %s, skipping test scoring',
            submission_id,
        )

    except Exception:
        logger.exception(
            'Test scoring failed for submission %s', submission_id,
        )

    finally:
        try:
            orchestrator.cleanup()
        except Exception:
            logger.exception(
                'Cleanup failed for test scoring of submission %s',
                submission_id,
            )
