"""Test ownership and recovery of official test scoring claims."""
import uuid
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from challenge.enums import DatasetType, SubmissionStatus
from challenge.models import Submission
from challenge.services import LocalContainerOrchestrator
from challenge.tasks import process_test_scoring


class TestScoringClaims(TestCase):
    fixtures = ['demo-user.json', 'demo-challenge.json']

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
            timezone.now() - timezone.timedelta(minutes=121))
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

    def test_expired_attempt_cannot_write_submission_error(self):
        current_claim_id = uuid.uuid4()
        self.submission.test_scoring_in_progress = True
        self.submission.test_scoring_claim_id = current_claim_id
        self.submission.save(update_fields=[
            'test_scoring_in_progress', 'test_scoring_claim_id',
        ])

        current_attempt = LocalContainerOrchestrator(
            self.submission, attempt_id=current_claim_id.hex)
        current_attempt._save_submission_field(
            'error_message', 'current failure')
        old_attempt = LocalContainerOrchestrator(
            self.submission, attempt_id=uuid.uuid4().hex)
        old_attempt._save_submission_field('error_message', 'old failure')

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.error_message, 'current failure')
        self.assertEqual(self.submission.test_scoring_claim_id, current_claim_id)
