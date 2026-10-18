"""
Tests for the challenge app.

Run with: ENABLE_CHALLENGES=True python manage.py test challenge
"""
from django.test import TestCase
from django.utils import timezone

from challenge.enums import (
    ChallengePhase,
    DatasetType,
    SubmissionStatus,
)
from challenge.forms import CodeSubmissionForm, ChallengeConfigForm


class ChallengeModelTests(TestCase):
    """Tests for Challenge model properties and constraints."""

    def setUp(self):
        # These tests require a PublishedProject and User to exist.
        # In integration tests, use fixtures or factory methods.
        pass

    def test_challenge_phase_choices(self):
        """Verify all expected phase choices exist."""
        phases = [c[0] for c in ChallengePhase.choices]
        self.assertIn('registration', phases)
        self.assertIn('unofficial', phases)
        self.assertIn('official', phases)
        self.assertIn('results', phases)
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

    def test_dataset_type_choices(self):
        """Verify dataset type choices."""
        types = [c[0] for c in DatasetType.choices]
        self.assertIn('val', types)
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
