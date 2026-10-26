"""
Tests for the challenge app.

Run with: ENABLE_CHALLENGES=True python manage.py test challenge
"""
import unittest
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from challenge.forms import CodeSubmissionForm, ChallengeConfigForm
from challenge.models import (
    Challenge,
    ChallengeConfiguration,
    ChallengeParticipant,
    Submission,
    Team,
    TeamInvitation,
)
from project.models import ActiveProject, PublishedProject
from user.models import User
from user.test_views import TestMixin


class ChallengeIntegrityTests(TestCase):
    """Tests for the challenge checks in ActiveProject.check_integrity()."""
    fixtures = [
        'demo-training-type.json', 'demo-user.json',
        'site-data.json', 'demo-project.json',
    ]

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
            validation_data_gcs_uri='challenge-staging/data/val',
            test_data_gcs_uri='challenge-staging/data/test',
            validation_labels_gcs_uri='challenge-staging/labels/val',
            test_labels_gcs_uri='challenge-staging/labels/test',
            evaluation_script_gcs_uri='challenge-staging/eval/evaluate.py',
        )
        passed, errors = self.check()
        self.assertTrue(passed, errors)

    def test_input_data_required_for_publication(self):
        now = timezone.now()
        config = ChallengeConfiguration.objects.create(
            active_project_id=self.project_id,
            start_datetime=now,
            end_datetime=now + timezone.timedelta(days=30),
            primary_metric={'name': 'auc', 'sort': 'desc'},
            validation_labels_gcs_uri='challenge-staging/labels/val',
            test_labels_gcs_uri='challenge-staging/labels/test',
            evaluation_script_gcs_uri='challenge-staging/eval/evaluate.py',
        )
        passed, errors = self.check()
        self.assertFalse(passed)
        self.assertIn('Validation data must be uploaded for scoring.', errors)
        self.assertIn('Test data must be uploaded for scoring.', errors)

        config.validation_data_gcs_uri = 'challenge-staging/data/val'
        config.test_data_gcs_uri = 'challenge-staging/data/test'
        config.save(update_fields=[
            'validation_data_gcs_uri', 'test_data_gcs_uri',
        ])
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


@unittest.skipUnless(
    getattr(settings, 'ENABLE_CHALLENGES', False),
    'Challenge URLs not registered',
)
class ChallengeAuthTests(TestCase):
    """Tests for the challenge_auth decorator and view authorization."""
    fixtures = ['demo-user.json', 'demo-challenge.json']

    def setUp(self):
        self.client = Client()
        self.challenge = Challenge.objects.get(slug='demo-ecg-challenge')
        self.participant_user = User.objects.get(username='rgmark')
        self.non_participant = User.objects.get(username='aewj')
        self.organizer = self.challenge.organizer

    def test_anonymous_gets_403_on_participant_view(self):
        """Anonymous users get 403 on participant-only views."""
        url = reverse('challenge_submit', args=[self.challenge.slug])
        response = self.client.get(url)
        # login_required redirects to login (302)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_non_participant_gets_403_on_participant_view(self):
        """Non-participants get 403 on require_participant views."""
        self.client.force_login(self.non_participant)
        url = reverse(
            'challenge_my_submissions', args=[self.challenge.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_participant_can_access_participant_view(self):
        """Registered participants can access participant-only views."""
        self.client.force_login(self.participant_user)
        url = reverse(
            'challenge_my_submissions', args=[self.challenge.slug])
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 302])

    def test_non_organizer_gets_403_on_manage_view(self):
        """Non-organizers get 403 on require_organizer views."""
        self.client.force_login(self.participant_user)
        url = reverse('challenge_manage', args=[self.challenge.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_organizer_can_access_manage_view(self):
        """The challenge organizer can access manage views."""
        self.client.force_login(self.organizer)
        url = reverse('challenge_manage', args=[self.challenge.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_submission_detail_idor_blocked(self):
        """A participant cannot view another participant's solo submission."""
        # Create a second participant
        other_user = User.objects.get(username='tompollard')
        ChallengeParticipant.objects.create(
            user=other_user, challenge=self.challenge,
        )

        # Get the existing submission (belongs to rgmark)
        submission = Submission.objects.get(
            challenge=self.challenge, submitted_by=self.participant_user,
        )

        # Log in as the other participant
        self.client.force_login(other_user)
        url = reverse(
            'challenge_submission_detail',
            args=[self.challenge.slug, submission.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_submitter_can_view_own_submission(self):
        """The submitter can view their own submission."""
        self.client.force_login(self.participant_user)
        submission = Submission.objects.get(
            challenge=self.challenge, submitted_by=self.participant_user,
        )
        url = reverse(
            'challenge_submission_detail',
            args=[self.challenge.slug, submission.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_organizer_can_view_submission_without_registering(self):
        """Organizers can view any submission without being participants."""
        self.assertFalse(ChallengeParticipant.objects.filter(
            user=self.organizer, challenge=self.challenge).exists())
        submission = Submission.objects.get(
            challenge=self.challenge, submitted_by=self.participant_user,
        )
        self.client.force_login(self.organizer)
        url = reverse(
            'challenge_submission_detail',
            args=[self.challenge.slug, submission.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


@unittest.skipUnless(
    getattr(settings, 'ENABLE_CHALLENGES', False),
    'Challenge URLs not registered',
)
class TeamInvitationTests(TestCase):
    """Responding to team invitations."""
    fixtures = ['demo-user.json', 'demo-challenge.json']

    def setUp(self):
        self.challenge = Challenge.objects.get(slug='demo-ecg-challenge')
        self.team = Team.objects.get(challenge=self.challenge, name='BioSignal Lab')
        self.captain = User.objects.get(username='jameslawson')
        # rgmark is registered and not on a team
        self.invitee = User.objects.get(username='rgmark')
        self.client.force_login(self.invitee)

    def _invite(self, team=None, email=None):
        return TeamInvitation.objects.create(
            team=team or self.team,
            email=email or self.invitee.email,
            invited_by=self.captain,
        )

    def _respond_url(self, invitation, challenge=None):
        return reverse('challenge_team_invitation_respond',
                       args=[(challenge or self.challenge).slug, invitation.pk])

    def test_accept_invitation(self):
        invitation = self._invite()
        response = self.client.post(self._respond_url(invitation), {'accept': True})
        self.assertRedirects(response, reverse('challenge_team', args=[self.challenge.slug]))
        participant = ChallengeParticipant.objects.get(
            user=self.invitee, challenge=self.challenge)
        self.assertEqual(participant.team, self.team)

    def test_email_match_is_case_insensitive(self):
        invitation = self._invite(email=self.invitee.email.upper())
        response = self.client.get(self._respond_url(invitation))
        self.assertEqual(response.status_code, 200)

    def test_invitation_for_someone_else_not_found(self):
        invitation = self._invite(email='someone-else@example.com')
        response = self.client.get(self._respond_url(invitation))
        self.assertEqual(response.status_code, 404)

    def test_invitation_from_another_challenge_not_found(self):
        """An invitation can only be used within its own challenge."""
        other_project = PublishedProject.objects.filter(challenge=None).first()
        other_challenge = Challenge.objects.create(
            published_project=other_project, slug='other-challenge',
            organizer=self.captain, teams_enabled=True,
        )
        other_team = Team.objects.create(challenge=other_challenge, name='Other')
        invitation = self._invite(team=other_team)
        response = self.client.post(self._respond_url(invitation), {'accept': True})
        self.assertEqual(response.status_code, 404)
        participant = ChallengeParticipant.objects.get(
            user=self.invitee, challenge=self.challenge)
        self.assertIsNone(participant.team)

    def test_cannot_join_second_team(self):
        participant = ChallengeParticipant.objects.get(
            user=self.invitee, challenge=self.challenge)
        participant.team = Team.objects.get(challenge=self.challenge, name='ICU Predictors')
        participant.save()
        invitation = self._invite()
        self.client.post(self._respond_url(invitation), {'accept': True})
        participant.refresh_from_db()
        self.assertEqual(participant.team.name, 'ICU Predictors')
        invitation.refresh_from_db()
        self.assertIsNone(invitation.response)

    def test_unregistered_invitee_sent_to_registration(self):
        ChallengeParticipant.objects.filter(
            user=self.invitee, challenge=self.challenge).update(is_active=False)
        invitation = self._invite()
        response = self.client.get(self._respond_url(invitation))
        self.assertRedirects(
            response, reverse('challenge_register', args=[self.challenge.slug]),
            fetch_redirect_response=False)

    def test_invitation_listed_on_team_page(self):
        invitation = self._invite()
        response = self.client.get(reverse('challenge_team', args=[self.challenge.slug]))
        self.assertContains(response, self._respond_url(invitation))


@unittest.skipUnless(
    getattr(settings, 'ENABLE_CHALLENGES', False),
    'Challenge URLs not registered',
)
class CodeSubmissionTests(TestCase):
    """Uploading a code submission."""
    fixtures = ['demo-user.json', 'demo-challenge.json']

    def setUp(self):
        self.challenge = Challenge.objects.get(slug='demo-ecg-challenge')
        self.user = User.objects.get(username='rgmark')
        self.client.force_login(self.user)
        self.url = reverse('challenge_submit', args=[self.challenge.slug])

    def _post(self):
        archive = SimpleUploadedFile('code.zip', b'PK\x03\x04', content_type='application/zip')
        return self.client.post(self.url, {'code_archive': archive})

    @override_settings(CHALLENGE_STAGING_BUCKET='')
    def test_rejected_when_bucket_not_configured(self):
        before = Submission.objects.count()
        with patch('challenge.views._upload_code_archive') as upload:
            self._post()
        upload.assert_not_called()
        self.assertEqual(Submission.objects.count(), before)

    @override_settings(CHALLENGE_STAGING_BUCKET='staging-bucket')
    def test_submission_created_and_queued(self):
        before = Submission.objects.filter(submitted_by=self.user).count()
        with patch('challenge.views._upload_code_archive',
                   return_value='staging-bucket/code.zip'), \
                patch('challenge.tasks.process_submission') as task, \
                self.captureOnCommitCallbacks(execute=True):
            response = self._post()
        submission = Submission.objects.filter(submitted_by=self.user).latest('pk')
        self.assertRedirects(
            response,
            reverse('challenge_submission_detail', args=[self.challenge.slug, submission.pk]),
            fetch_redirect_response=False)
        self.assertEqual(Submission.objects.filter(submitted_by=self.user).count(), before + 1)
        task.assert_called_once_with(submission.pk)

    @override_settings(CHALLENGE_STAGING_BUCKET='staging-bucket')
    def test_daily_limit_enforced(self):
        self.challenge.max_submissions_per_day = Submission.objects.filter(
            challenge=self.challenge, submitted_by=self.user,
            created_datetime__date=timezone.localdate(),
        ).count()
        self.challenge.save()
        before = Submission.objects.count()
        with patch('challenge.views._upload_code_archive') as upload:
            self._post()
        upload.assert_not_called()
        self.assertEqual(Submission.objects.count(), before)


@unittest.skipUnless(
    getattr(settings, 'ENABLE_CHALLENGES', False),
    'Challenge URLs not registered',
)
class SubmissionSelectTests(TestCase):
    """Selecting a submission updates the leaderboard entry and ranks."""
    fixtures = ['demo-user.json', 'demo-challenge.json']

    def test_select_updates_entry_and_ranks(self):
        challenge = Challenge.objects.get(slug='demo-ecg-challenge')
        captain = ChallengeParticipant.objects.get(
            challenge=challenge, team__name='BioSignal Lab', is_team_captain=True,
        ).user
        self.client.force_login(captain)
        response = self.client.post(
            reverse('challenge_submission_select', args=[challenge.slug, 1]))
        self.assertEqual(response.status_code, 302)

        from challenge.tasks import recompute_leaderboard
        recompute_leaderboard.now(challenge.pk)
        entries = challenge.leaderboard_entries.filter(dataset='val').order_by('rank')
        self.assertEqual(
            [(e.team.name if e.team else e.user.username, e.primary_score) for e in entries],
            [('ICU Predictors', 0.873), ('franwilliams', 0.789), ('BioSignal Lab', 0.762)],
        )
