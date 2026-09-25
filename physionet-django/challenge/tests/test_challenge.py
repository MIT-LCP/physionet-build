"""
Tests for the challenge app.

Run with: ENABLE_CHALLENGES=True python manage.py test challenge
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, RequestFactory
from django.utils import timezone

from challenge.enums import (
    ChallengePhase,
    DatasetType,
    MetricSort,
    SubmissionStatus,
)
from challenge.forms import CodeSubmissionForm, ChallengeConfigForm
from challenge.models import (
    Challenge,
    ChallengeParticipant,
    LeaderboardEntry,
    Score,
    Submission,
    SubmissionSpec,
    Team,
    TeamInvitation,
)


class ChallengeModelTests(TestCase):
    """Tests for Challenge model properties and constraints."""

    def setUp(self):
        # These tests require a PublishedProject and User to exist.
        # In integration tests, use fixtures or factory methods.
        pass

    def test_challenge_phase_choices(self):
        """Verify all expected phase choices exist."""
        phases = [c[0] for c in ChallengePhase.choices]
        self.assertIn('setup', phases)
        self.assertIn('active', phases)
        self.assertIn('evaluation', phases)
        self.assertIn('completed', phases)
        self.assertIn('archived', phases)

    def test_submission_status_choices(self):
        """Verify all expected submission status choices exist."""
        statuses = [c[0] for c in SubmissionStatus.choices]
        self.assertIn('pending', statuses)
        self.assertIn('building', statuses)
        self.assertIn('running', statuses)
        self.assertIn('scoring', statuses)
        self.assertIn('completed', statuses)
        self.assertIn('failed', statuses)
        self.assertIn('cancelled', statuses)
        self.assertIn('timed_out', statuses)

    def test_metric_sort_choices(self):
        """Verify metric sort choices."""
        sorts = [c[0] for c in MetricSort.choices]
        self.assertIn('asc', sorts)
        self.assertIn('desc', sorts)

    def test_dataset_type_choices(self):
        """Verify dataset type choices."""
        types = [c[0] for c in DatasetType.choices]
        self.assertIn('dev', types)
        self.assertIn('test', types)


class CodeSubmissionFormTests(TestCase):
    """Tests for the code submission form validation."""

    def test_rejects_invalid_extension(self):
        """Form should reject files without .tar.gz or .zip extension."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('code.py', b'print("hello")')
        form = CodeSubmissionForm(data={'description': ''}, files={'code_archive': f})
        self.assertFalse(form.is_valid())
        self.assertIn('code_archive', form.errors)

    def test_accepts_tar_gz(self):
        """Form should accept .tar.gz files within size limits."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('code.tar.gz', b'\x00' * 100)
        form = CodeSubmissionForm(data={'description': ''}, files={'code_archive': f})
        self.assertTrue(form.is_valid())

    def test_accepts_zip(self):
        """Form should accept .zip files within size limits."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('code.zip', b'\x00' * 100)
        form = CodeSubmissionForm(data={'description': ''}, files={'code_archive': f})
        self.assertTrue(form.is_valid())


class ChallengeConfigFormTests(TestCase):
    """Tests for challenge configuration form validation."""

    def test_end_before_start_rejected(self):
        """Form should reject end datetime before start datetime."""
        now = timezone.now()
        form = ChallengeConfigForm(data={
            'start_datetime': now + timezone.timedelta(days=2),
            'end_datetime': now + timezone.timedelta(days=1),
            'max_submissions_per_day': 5,
            'max_total_submissions': 100,
            'teams_enabled': False,
            'is_active': True,
            'rules': '',
            'evaluation_description': '',
            'prizes': '',
        })
        self.assertFalse(form.is_valid())
