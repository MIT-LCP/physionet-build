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
    from challenge.services import ContainerOrchestrator
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

    orchestrator = ContainerOrchestrator(submission)

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

    for dataset in [DatasetType.DEV, DatasetType.TEST]:
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


def _save_scores(submission, scores_data):
    """Parse and save Score objects from the scoring output."""
    score_objects = []
    for metric_name, value in scores_data.items():
        score_objects.append(Score(
            submission=submission,
            metric_name=metric_name,
            value=float(value),
            dataset=DatasetType.DEV,
        ))
    Score.objects.bulk_create(score_objects)


def _update_leaderboard_entry(submission):
    """
    Update the leaderboard entry for this submission's participant/team.
    If this submission is better than their current entry, replace it.
    """
    challenge = submission.challenge
    spec = challenge.submission_spec
    sort_ascending = spec.primary_metric_sort == MetricSort.ASC

    primary_score = submission.scores.filter(
        metric_name=spec.primary_metric_name,
        dataset=DatasetType.DEV,
    ).first()

    if not primary_score:
        return

    all_scores = {
        s.metric_name: s.value
        for s in submission.scores.filter(dataset=DatasetType.DEV)
    }

    lookup = {
        'challenge': challenge,
        'dataset': DatasetType.DEV,
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
