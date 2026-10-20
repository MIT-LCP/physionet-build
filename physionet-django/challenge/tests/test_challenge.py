"""
Tests for the challenge app.

Run with: ENABLE_CHALLENGES=True python manage.py test challenge
"""
import unittest

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from challenge.forms import CodeSubmissionForm, ChallengeConfigForm
from challenge.models import ChallengeConfiguration
from project.models import ActiveProject
from user.test_views import TestMixin


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


class ChallengeNewVersionTests(TestCase):
    """Test that ChallengeConfiguration is copied when creating a new version."""
    fixtures = ['demo-user.json', 'demo-challenge.json']

    @override_settings(COPY_FILES_TO_NEW_VERSION=False)
    def test_new_version_copies_challenge_config(self):
        from project.forms import NewProjectVersionForm
        from project.models import PublishedProject

        published = PublishedProject.objects.get(slug='demo-ecg-challenge')
        user = published.submitting_user()
        previous = PublishedProject.objects.filter(
            slug='demo-ecg-challenge',
        ).order_by('-version_order')

        form = NewProjectVersionForm(
            user=user,
            latest_project=published,
            previous_projects=previous,
            data={'version': '2.0.0'},
        )
        self.assertTrue(form.is_valid(), form.errors)
        new_project = form.save()

        self.assertTrue(
            hasattr(new_project, 'challenge_config'),
        )
        config = new_project.challenge_config
        challenge = published.challenge
        spec = challenge.submission_spec

        self.assertEqual(config.max_submissions_per_day, challenge.max_submissions_per_day)
        self.assertEqual(config.teams_enabled, challenge.teams_enabled)
        self.assertEqual(config.start_datetime, challenge.start_datetime)
        self.assertEqual(config.base_image, spec.base_image)
        self.assertEqual(config.entrypoint_command, spec.entrypoint_command)
        self.assertEqual(config.max_runtime_seconds, spec.max_runtime_seconds)
        self.assertEqual(config.primary_metric, spec.primary_metric)


@unittest.skipUnless(
    getattr(settings, 'ENABLE_CHALLENGES', False),
    'Challenge URLs not registered',
)
class PublishedChallengePageTests(TestMixin):
    """The published project page shows challenge content."""

    def setUp(self):
        super().setUp()
        self.url = reverse('published_project', args=['demo-ecg-challenge', '1.0.0'])

    def test_challenge_tabs_rendered(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'challenge-tabs')
        self.assertContains(response, 'id="challenge-tab-leaderboard"')
        self.assertContains(response, 'id="challenge-tab-rules"')

    @override_settings(ENABLE_CHALLENGES=False)
    def test_challenge_content_hidden_when_disabled(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'challenge-tabs')

    def test_detail_redirects_to_published_project(self):
        response = self.client.get(
            reverse('challenge_detail', args=['demo-ecg-challenge']))
        self.assertRedirects(response, self.url)


class ChallengeConfigViewTests(TestCase):
    """Tests for the Challenge Setup step of an active project."""

    def setUp(self):
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.resource_type_id = 2
        project.save()
        self.project = project
        self.url = reverse('project_challenge_config', args=[project.slug])
        self.client.force_login(project.authors.get(is_submitting=True).user)

    def test_get_does_not_create_config(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ChallengeConfiguration.objects.filter(active_project=self.project).exists())

    def test_all_fields_rendered(self):
        response = self.client.get(self.url)
        for name in response.context['challenge_config_form'].fields:
            self.assertContains(response, f'name="{name}"')

    def test_post_saves_config(self):
        response = self.client.post(self.url, data={
            'organizer_name': 'Organizer',
            'start_datetime': '2030-01-01T00:00',
            'official_start_datetime': '2030-02-01T00:00',
            'end_datetime': '2030-03-01T00:00',
            'max_submissions_per_day': 5,
            'max_total_submissions': 100,
            'max_submissions_to_advance': 1,
            'base_image': 'python:3.11-slim',
            'entrypoint_command': 'python main.py',
            'max_runtime_seconds': 3600,
            'max_memory_mb': 4096,
            'cpu_count': 2,
            'input_format': '{}',
            'output_format': '{}',
            'primary_metric': '{"name": "auc", "sort": "desc"}',
            'additional_metrics': '[]',
        })
        self.assertEqual(response.status_code, 200)
        config = ChallengeConfiguration.objects.get(active_project=self.project)
        self.assertEqual(config.organizer_name, 'Organizer')
        self.assertIsNotNone(config.official_start_datetime)
        self.assertEqual(config.primary_metric, {'name': 'auc', 'sort': 'desc'})

    def test_step_headers_match_sidebar(self):
        response = self.client.get(reverse('project_upload_agreement', args=[self.project.slug]))
        self.assertContains(response, '<h2 class="form-signin-heading">7. Upload Agreement</h2>', html=True)
