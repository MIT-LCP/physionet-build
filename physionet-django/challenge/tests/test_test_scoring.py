"""Test ownership and recovery of official test scoring claims."""
import uuid
import unittest
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from challenge.enums import DatasetType, SubmissionStatus
from challenge.models import Score, Submission
from challenge.services import LocalContainerOrchestrator
from challenge.tasks import _select_top_n, process_test_scoring


class TestScoringClaims(TestCase):
    fixtures = [
        'demo-training-type.json', 'demo-user.json',
        'site-data.json', 'project-types.json', 'demo-challenge.json',
    ]

    def setUp(self):
        self.submission = Submission.objects.get(status=SubmissionStatus.PENDING)

    def test_success_completes_and_releases_claim(self):
        orchestrator = mock.MagicMock()
        orchestrator.poll.return_value = True
        orchestrator.extract_scores.return_value = {'AUROC': 0.8}

        with mock.patch('challenge.services.get_orchestrator',
                        return_value=orchestrator) as get_orchestrator:
            process_test_scoring.now(self.submission.pk)

        self.submission.refresh_from_db()
        self.assertTrue(self.submission.test_scoring_complete)
        self.assertFalse(self.submission.test_scoring_in_progress)
        self.assertIsNone(self.submission.test_scoring_claim_id)
        self.assertIsNone(self.submission.test_scoring_claimed_at)
        self.assertEqual(
            self.submission.scores.get(dataset=DatasetType.TEST).value, 0.8)
        self.assertEqual(
            len(get_orchestrator.call_args.kwargs['attempt_id']), 32)

    def test_old_worker_cannot_save_or_release_new_claim(self):
        new_claim_id = uuid.uuid4()
        orchestrator = mock.MagicMock()
        orchestrator.poll.return_value = True
        orchestrator.extract_scores.return_value = {'AUROC': 0.9}

        def replace_claim(*args, **kwargs):
            Submission.objects.filter(pk=self.submission.pk).update(
                test_scoring_claim_id=new_claim_id,
                test_scoring_claimed_at=timezone.now(),
            )

        orchestrator.run.side_effect = replace_claim
        with mock.patch('challenge.services.get_orchestrator',
                        return_value=orchestrator):
            process_test_scoring.now(self.submission.pk)

        self.submission.refresh_from_db()
        self.assertFalse(self.submission.test_scoring_complete)
        self.assertTrue(self.submission.test_scoring_in_progress)
        self.assertEqual(self.submission.test_scoring_claim_id, new_claim_id)
        self.assertFalse(
            self.submission.scores.filter(dataset=DatasetType.TEST).exists())

    def test_stale_claim_can_be_reclaimed(self):
        self.submission.test_scoring_in_progress = True
        self.submission.test_scoring_claim_id = uuid.uuid4()
        self.submission.test_scoring_claimed_at = (
            timezone.now() - timezone.timedelta(minutes=183))
        self.submission.save(update_fields=[
            'test_scoring_in_progress', 'test_scoring_claim_id',
            'test_scoring_claimed_at',
        ])
        orchestrator = mock.MagicMock()
        orchestrator.poll.return_value = True
        orchestrator.extract_scores.return_value = {'AUROC': 0.7}

        with mock.patch('challenge.services.get_orchestrator',
                        return_value=orchestrator):
            process_test_scoring.now(self.submission.pk)

        self.submission.refresh_from_db()
        self.assertTrue(self.submission.test_scoring_complete)
        self.assertEqual(
            self.submission.scores.get(dataset=DatasetType.TEST).value, 0.7)

    def test_claim_survives_full_container_runtime(self):
        self.submission.test_scoring_in_progress = True
        self.submission.test_scoring_claim_id = uuid.uuid4()
        self.submission.test_scoring_claimed_at = (
            timezone.now() - timezone.timedelta(minutes=121))
        self.submission.save(update_fields=[
            'test_scoring_in_progress', 'test_scoring_claim_id',
            'test_scoring_claimed_at',
        ])

        with mock.patch('challenge.services.get_orchestrator') as get_orchestrator:
            process_test_scoring.now(self.submission.pk)

        get_orchestrator.assert_not_called()
        self.submission.refresh_from_db()
        self.assertTrue(self.submission.test_scoring_in_progress)

    def test_expired_attempt_cannot_write_test_scoring_error(self):
        current_claim_id = uuid.uuid4()
        self.submission.test_scoring_in_progress = True
        self.submission.test_scoring_claim_id = current_claim_id
        self.submission.save(update_fields=[
            'test_scoring_in_progress', 'test_scoring_claim_id',
        ])

        current_attempt = LocalContainerOrchestrator(
            self.submission, attempt_id=current_claim_id.hex)
        current_attempt._save_run_error('current failure', DatasetType.TEST)
        old_attempt = LocalContainerOrchestrator(
            self.submission, attempt_id=uuid.uuid4().hex)
        old_attempt._save_run_error('old failure', DatasetType.TEST)

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.error_message, '')
        self.assertEqual(
            self.submission.test_scoring_error_message, 'current failure')
        self.assertEqual(self.submission.test_scoring_claim_id, current_claim_id)

    @unittest.skipUnless(
        getattr(settings, 'ENABLE_CHALLENGES', False),
        'Challenge URLs not registered',
    )
    def test_test_run_logs_are_hidden_from_participant(self):
        self.submission.test_scoring_in_progress = True
        self.submission.test_scoring_claim_id = uuid.uuid4()
        self.submission.save(update_fields=[
            'test_scoring_in_progress', 'test_scoring_claim_id',
        ])
        LocalContainerOrchestrator(
            self.submission,
            attempt_id=self.submission.test_scoring_claim_id.hex,
        )._save_run_error('hidden patient data', DatasetType.TEST)

        args = [self.submission.challenge.slug, self.submission.pk]
        detail_url = reverse('challenge_submission_detail', args=args)
        status_url = reverse('challenge_submission_status_detail', args=args)

        self.client.force_login(self.submission.submitted_by)
        detail = self.client.get(detail_url)
        status = self.client.get(status_url).json()
        self.assertContains(detail, 'Official test scoring failed.')
        self.assertNotContains(detail, 'hidden patient data')
        self.assertIn('Official test scoring failed.', status['error_message'])
        self.assertNotIn('hidden patient data', status['error_message'])

        self.client.force_login(self.submission.challenge.organizer)
        self.assertContains(self.client.get(detail_url), 'hidden patient data')
        self.assertIn(
            'hidden patient data',
            self.client.get(status_url).json()['error_message'],
        )

    def test_equal_scores_use_creation_time_then_submission_id(self):
        challenge = self.submission.challenge
        submissions = [Submission.objects.create(
            challenge=challenge,
            submitted_by=self.submission.submitted_by,
            code_archive_gcs_uri='challenge-staging/example.tar.gz',
            status=SubmissionStatus.COMPLETED,
        ) for _ in range(2)]
        for submission in submissions:
            Score.objects.create(
                submission=submission, metric_name='AUROC',
                dataset=DatasetType.VAL, value=0.8,
            )
        older = timezone.now() - timezone.timedelta(days=1)
        Submission.objects.filter(pk=submissions[1].pk).update(
            created_datetime=older)
        queryset = Submission.objects.filter(
            pk__in=[submission.pk for submission in submissions])

        with mock.patch('challenge.tasks.process_test_scoring') as enqueue:
            _select_top_n(queryset, challenge.submission_spec, 1, False)
        enqueue.assert_called_once_with(submissions[1].pk)

        Submission.objects.filter(pk__in=[s.pk for s in submissions]).update(
            created_datetime=older)
        with mock.patch('challenge.tasks.process_test_scoring') as enqueue:
            _select_top_n(queryset, challenge.submission_spec, 1, False)
        enqueue.assert_called_once_with(submissions[0].pk)
