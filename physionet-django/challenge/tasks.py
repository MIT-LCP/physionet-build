"""
Background tasks for challenge phase transitions.
"""
import logging
import uuid

from background_task import background
from django.db import transaction
from django.utils import timezone

from challenge.enums import DatasetType, MetricSort, SubmissionStatus
from challenge.models import Challenge, LeaderboardEntry, Score, Submission
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

        # Save scores and update leaderboard atomically
        with transaction.atomic():
            _save_scores(submission, scores_data)
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
        with transaction.atomic():
            entries = LeaderboardEntry.objects.select_for_update().filter(
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
        raise ValueError(
            f'Primary metric {spec.primary_metric_name!r} not found in '
            f'scores for submission {submission.pk} ({dataset.label}).'
        )

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
            # Manual selection only applies to the validation leaderboard.
            # Test entries are always replaced by a better result.
            has_manual_selection = (
                dataset == DatasetType.VAL
                and Submission.objects.filter(
                    challenge=challenge,
                    is_selected=True,
                    status=SubmissionStatus.COMPLETED,
                    **({'team': submission.team} if submission.team
                       else {'submitted_by': submission.submitted_by,
                             'team__isnull': True}),
                ).exists()
            )

            if not has_manual_selection:
                is_better = (
                    (sort_ascending
                     and primary_score.value < entry.primary_score)
                    or (not sort_ascending
                        and primary_score.value > entry.primary_score)
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
        # Group by team (team-based submissions)
        team_ids = completed_submissions.exclude(
            team__isnull=True,
        ).values_list('team_id', flat=True).distinct()

        for team_id in team_ids:
            team_subs = completed_submissions.filter(team_id=team_id)
            _select_top_n(team_subs, spec, n, sort_ascending)

        # Solo submissions (participants who never joined a team)
        solo_user_ids = completed_submissions.filter(
            team__isnull=True,
        ).values_list('submitted_by_id', flat=True).distinct()

        for user_id in solo_user_ids:
            user_subs = completed_submissions.filter(
                submitted_by_id=user_id, team__isnull=True)
            _select_top_n(user_subs, spec, n, sort_ascending)
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

    already_complete = set(
        Submission.objects.filter(
            pk__in=submission_ids,
            test_scoring_complete=True,
        ).values_list('pk', flat=True)
    )
    for sub_id in submission_ids:
        if sub_id not in already_complete:
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

    # Atomically claim this submission for test scoring.  Only one
    # worker proceeds; the rest return immediately.
    STALE_CLAIM_MINUTES = 120
    claim_id = uuid.uuid4()
    with transaction.atomic():
        locked = Submission.objects.select_for_update().filter(
            pk=submission_id,
            test_scoring_complete=False,
        ).first()
        if not locked:
            logger.info(
                'Submission %s already completed test scoring, skipping',
                submission_id,
            )
            return
        if locked.test_scoring_in_progress:
            cutoff = timezone.now() - timezone.timedelta(
                minutes=STALE_CLAIM_MINUTES)
            if locked.test_scoring_claimed_at and locked.test_scoring_claimed_at > cutoff:
                logger.info(
                    'Submission %s claimed by another worker, skipping',
                    submission_id,
                )
                return
            logger.warning(
                'Submission %s has stale claim, reclaiming',
                submission_id,
            )
        locked.scores.filter(dataset=DatasetType.TEST).delete()
        locked.test_scoring_in_progress = True
        locked.test_scoring_claimed_at = timezone.now()
        locked.test_scoring_claim_id = claim_id
        locked.save(update_fields=[
            'test_scoring_in_progress', 'test_scoring_claimed_at',
            'test_scoring_claim_id',
        ])

    succeeded = False
    orchestrator = None

    try:
        submission.refresh_from_db()
        orchestrator = get_orchestrator(submission, attempt_id=claim_id.hex)

        orchestrator.build()
        orchestrator.run(dataset=DatasetType.TEST)

        success = orchestrator.poll()
        if not success:
            logger.error(
                'Test scoring failed for submission %s', submission_id,
            )
            return

        scores_data = orchestrator.extract_scores()
        with transaction.atomic():
            current_claim = Submission.objects.select_for_update().filter(
                pk=submission_id,
                test_scoring_complete=False,
                test_scoring_in_progress=True,
                test_scoring_claim_id=claim_id,
            ).first()
            if not current_claim:
                logger.warning(
                    'Submission %s test scoring claim expired; discarding results',
                    submission_id,
                )
                return
            _save_scores(submission, scores_data, dataset=DatasetType.TEST)
            _update_leaderboard_entry(submission, dataset=DatasetType.TEST)
            current_claim.test_scoring_complete = True
            current_claim.test_scoring_in_progress = False
            current_claim.test_scoring_claimed_at = None
            current_claim.test_scoring_claim_id = None
            current_claim.save(update_fields=[
                'test_scoring_complete', 'test_scoring_in_progress',
                'test_scoring_claimed_at', 'test_scoring_claim_id',
            ])
        succeeded = True

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
        if not succeeded:
            Submission.objects.filter(
                pk=submission_id,
                test_scoring_claim_id=claim_id,
                test_scoring_in_progress=True,
                test_scoring_complete=False,
            ).update(
                test_scoring_in_progress=False,
                test_scoring_claimed_at=None,
                test_scoring_claim_id=None,
            )
        if orchestrator:
            try:
                orchestrator.cleanup()
            except Exception:
                logger.exception(
                    'Cleanup failed for test scoring of submission %s',
                    submission_id,
                )
