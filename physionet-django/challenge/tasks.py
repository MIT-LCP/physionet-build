"""
Background tasks for challenge phase transitions.
"""
import logging

from background_task import background
from django.db import transaction

from challenge.enums import DatasetType, MetricSort, SubmissionStatus
from challenge.models import Challenge, LeaderboardEntry, Score, Submission
from console.tasks import associated_task

logger = logging.getLogger(__name__)


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


@associated_task(Submission, 'submission_id')
@background()
def process_submission(submission_id):
    """Process a submitted code archive. Replaced by the pipeline in #2790."""
    logger.info('process_submission(%s): stub — pipeline not yet installed',
                submission_id)


@associated_task(Challenge, 'challenge_id')
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
        with transaction.atomic():
            entries = LeaderboardEntry.objects.select_for_update().filter(
                challenge=challenge, dataset=dataset,
            ).order_by('primary_score' if sort_ascending else '-primary_score')

            for rank, entry in enumerate(entries, start=1):
                if entry.rank != rank:
                    entry.rank = rank
                    entry.save(update_fields=['rank'])


def _save_scores(submission, scores_data):
    """Parse and save Score objects from the scoring output."""
    score_objects = []
    for metric_name, value in scores_data.items():
        score_objects.append(Score(
            submission=submission,
            metric_name=metric_name,
            value=float(value),
            dataset=DatasetType.VAL,
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
        dataset=DatasetType.VAL,
    ).first()

    if not primary_score:
        return

    all_scores = {
        s.metric_name: s.value
        for s in submission.scores.filter(dataset=DatasetType.VAL)
    }

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

    with transaction.atomic():
        try:
            entry = LeaderboardEntry.objects.select_for_update().get(
                **lookup,
            )
        except LeaderboardEntry.DoesNotExist:
            LeaderboardEntry.objects.create(
                submission=submission,
                primary_score=primary_score.value,
                all_scores=all_scores,
                **lookup,
            )
        else:
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
