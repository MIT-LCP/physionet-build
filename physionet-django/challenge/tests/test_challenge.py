"""
Tests for the challenge app.

Run with: ENABLE_CHALLENGES=True python manage.py test challenge
"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from challenge.forms import CodeSubmissionForm, ChallengeConfigForm
from challenge.models import ChallengeConfiguration
from project.models import ActiveProject


class ChallengeIntegrityTests(TestCase):
    """Tests for the challenge checks in ActiveProject.check_integrity()."""

    def setUp(self):
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.resource_type_id = 2
        project.save()
        self.project_id = project.pk

    def check(self):
        project = ActiveProject.objects.get(pk=self.project_id)
        return project.check_integrity(), project.integrity_errors

    def test_challenge_without_config_passes(self):
        """Challenge-type projects that aren't hosted challenges can still be submitted."""
        passed, errors = self.check()
        self.assertTrue(passed, errors)

    def test_incomplete_config_rejected(self):
        ChallengeConfiguration.objects.create(active_project_id=self.project_id)
        passed, errors = self.check()
        self.assertFalse(passed)
        self.assertIn('Challenge start date is required.', errors)
        self.assertIn('Challenge end date is required.', errors)
        self.assertIn('Primary metric name is required.', errors)

    def test_complete_config_passes(self):
        now = timezone.now()
        ChallengeConfiguration.objects.create(
            active_project_id=self.project_id,
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=30),
            primary_metric={'name': 'auc', 'sort': 'desc'},
        )
        passed, errors = self.check()
        self.assertTrue(passed, errors)


class CodeSubmissionFormTests(TestCase):
    """Tests for the code submission form validation."""

    def test_rejects_invalid_extension(self):
        """Form should reject files without .tar.gz or .zip extension."""
        f = SimpleUploadedFile('code.py', b'print("hello")')
        form = CodeSubmissionForm(data={'description': ''}, files={'code_archive': f})
        self.assertFalse(form.is_valid())
        self.assertIn('code_archive', form.errors)

    def test_accepts_tar_gz(self):
        """Form should accept .tar.gz files within size limits."""
        f = SimpleUploadedFile('code.tar.gz', b'\x00' * 100)
        form = CodeSubmissionForm(data={'description': ''}, files={'code_archive': f})
        self.assertTrue(form.is_valid())

    def test_accepts_zip(self):
        """Form should accept .zip files within size limits."""
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
