import datetime
import importlib
from io import StringIO

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from project.models import ActiveProject, ArchiveReason, InternalNote, RevisionType, SubmissionStatus
from user.models import User
from user.test_views import TestMixin

PROJECT_TITLE = 'Demo software for parsing clinical notes'
EDITOR = 'tompollard'
PASSWORD = 'Tester11!'


def days_from_now(days):
    return timezone.now() + datetime.timedelta(days=days)


class RevisionDeadlineTestMixin(TestMixin):
    def setUp(self):
        super().setUp()
        self.project = ActiveProject.objects.get(title=PROJECT_TITLE)
        self.editor = User.objects.get(username=EDITOR)
        self.project.editor = self.editor
        self.project.save()

    def await_revisions(self, deadline, reminders_sent=None):
        """Put the project in NEEDS_RESUBMISSION with the given deadline."""
        project = self.project
        project.submission_status = SubmissionStatus.NEEDS_RESUBMISSION
        project.revision_request_datetime = timezone.now() - datetime.timedelta(days=60)
        project.set_revision_deadline(deadline)
        if reminders_sent is not None:
            project.revision_reminders_sent = reminders_sent
        project.save()
        return project

    def run_command(self, *args):
        out = StringIO()
        call_command('manage_revision_deadlines', *args, stdout=out)
        return out.getvalue()

    def author_emails(self):
        return {email for email, _ in self.project.author_contact_info()}


@override_settings(REVISION_DEADLINE_DAYS_MINOR=90, REVISION_DEADLINE_DAYS_MAJOR=180, REVISION_REMINDER_DAYS=(30, 7))
class TestRevisionDeadlineModel(RevisionDeadlineTestMixin):
    def test_request_revisions_sets_deadline(self):
        now = timezone.now()
        self.project.request_revisions(RevisionType.MINOR, now)
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)
        self.assertEqual(self.project.revision_deadline, now + datetime.timedelta(days=90))
        self.assertEqual(self.project.revision_reminders_sent, 0)

        self.project.request_revisions(RevisionType.MAJOR, now)
        self.assertEqual(self.project.revision_deadline, now + datetime.timedelta(days=180))

    def test_reminders_due(self):
        now = timezone.now()
        due = ActiveProject.revision_reminders_due
        self.assertEqual(due(now + datetime.timedelta(days=31), now), 0)
        self.assertEqual(due(now + datetime.timedelta(days=30), now), 1)
        self.assertEqual(due(now + datetime.timedelta(days=8), now), 1)
        self.assertEqual(due(now + datetime.timedelta(days=7), now), 2)
        self.assertEqual(due(now - datetime.timedelta(days=1), now), 2)

    def test_set_deadline_skips_reminders_already_due(self):
        self.await_revisions(days_from_now(10))
        self.assertEqual(self.project.revision_reminders_sent, 1)

    def test_resubmit_clears_deadline(self):
        self.await_revisions(days_from_now(60))
        self.project.resubmit(author_comments='Done')
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_DECISION)
        self.assertIsNone(self.project.revision_deadline)

    def test_reopen_only_for_reopenable_reasons(self):
        self.project.archive(archive_reason=ArchiveReason.REJECTED)
        self.assertFalse(self.project.is_reopenable())
        with self.assertRaises(Exception):
            self.project.reopen_for_revisions(days_from_now(30))

        self.project.archive_reason = ArchiveReason.REVISION_DEADLINE_PASSED
        self.project.save()
        self.assertTrue(self.project.is_reopenable())
        self.project.reopen_for_revisions(days_from_now(60))
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)
        self.assertIsNone(self.project.archive_reason)
        self.assertIsNone(self.project.archive_datetime)
        self.assertIsNotNone(self.project.revision_deadline)


@override_settings(REVISION_REMINDER_DAYS=(30, 7))
class TestManageRevisionDeadlinesCommand(RevisionDeadlineTestMixin):
    def test_no_reminder_before_first_threshold(self):
        self.await_revisions(days_from_now(45))
        self.run_command()
        self.assertEqual(len(mail.outbox), 0)

    def test_reminders_are_sent_once_per_threshold(self):
        self.await_revisions(days_from_now(60))
        # Move into the 30 day window
        ActiveProject.objects.filter(pk=self.project.pk).update(revision_deadline=days_from_now(29))
        self.run_command()
        self.assertEqual({e.to[0] for e in mail.outbox}, self.author_emails())
        self.assertIn('Reminder', mail.outbox[0].subject)
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision_reminders_sent, 1)

        # Running again does not repeat the reminder
        mail.outbox.clear()
        self.run_command()
        self.assertEqual(len(mail.outbox), 0)

        # Move into the 7 day window
        ActiveProject.objects.filter(pk=self.project.pk).update(revision_deadline=days_from_now(6))
        self.run_command()
        self.assertEqual(len(mail.outbox), len(self.author_emails()))
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision_reminders_sent, 2)
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)

    def test_project_archived_after_deadline(self):
        self.await_revisions(days_from_now(-1))
        self.run_command()
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.ARCHIVED)
        self.assertEqual(self.project.archive_reason, ArchiveReason.REVISION_DEADLINE_PASSED)
        recipients = {e.to[0] for e in mail.outbox}
        self.assertTrue(self.author_emails() <= recipients)
        self.assertIn(self.editor.email, recipients)
        # The project keeps its files, so it can be reopened
        self.assertTrue(self.project.is_reopenable())

    def test_projects_on_hold_are_skipped(self):
        self.await_revisions(days_from_now(-1))
        self.project.place_on_hold()
        self.run_command()
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)
        self.assertEqual(len(mail.outbox), 0)

    def test_projects_without_deadline_are_skipped(self):
        self.await_revisions(days_from_now(-1))
        ActiveProject.objects.filter(pk=self.project.pk).update(revision_deadline=None)
        self.run_command()
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)

    def test_dry_run_changes_nothing(self):
        self.await_revisions(days_from_now(-1))
        output = self.run_command('--dry-run')
        self.assertIn('Would archive', output)
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(REVISION_DEADLINE_DAYS_MINOR=90, REVISION_DEADLINE_DAYS_MAJOR=180)
class TestEditorDecision(TestMixin):
    def setUp(self):
        super().setUp()
        self.project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.project.submit(author_comments='')
        self.project.assign_editor(User.objects.get(username='admin'))
        self.project.submission_status = SubmissionStatus.NEEDS_DECISION
        self.project.save()

    def post_decision(self, **extra):
        self.client.login(username='admin', password=PASSWORD)
        data = {
            'soundly_produced': 1, 'well_described': 1, 'open_format': 1, 'data_machine_readable': 1,
            'reusable': 1, 'no_phi': 1, 'pn_suitable': 1, 'ethics_included': 1,
            'editor_comments': 'Please revise.', 'decision': 1, **extra,
        }
        return self.client.post(reverse('edit_submission', args=(self.project.slug,)), data=data)

    def test_major_revisions_deadline(self):
        before = timezone.now()
        self.post_decision(revision_type=RevisionType.MAJOR)
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)
        self.assertGreaterEqual(self.project.revision_deadline, before + datetime.timedelta(days=180))
        self.assertEqual(self.project.edit_logs.last().revision_type, RevisionType.MAJOR)
        # The decision email gives the deadline
        body = ' '.join(mail.outbox[0].body.split())
        deadline = date_format(timezone.localtime(self.project.revision_deadline), 'j F Y')
        self.assertIn(f'The editor has requested major revisions. Please resubmit your project by {deadline}.', body)

    def test_revision_type_required(self):
        response = self.post_decision()
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_DECISION)
        self.assertIsNone(self.project.revision_deadline)


class TestConsoleRevisionDeadline(RevisionDeadlineTestMixin):
    def url(self):
        return reverse('submission_info', args=(self.project.slug,))

    def test_editor_can_extend_deadline(self):
        self.await_revisions(days_from_now(5))
        new_date = timezone.localdate() + datetime.timedelta(days=60)
        self.client.login(username=EDITOR, password=PASSWORD)
        response = self.client.post(self.url(), {
            'extend_revision_deadline': '', 'revision_deadline': new_date.isoformat()})
        self.assertRedirects(response, f'{self.url()}?tab=revision-deadline', fetch_redirect_response=False)
        self.project.refresh_from_db()
        self.assertEqual(timezone.localdate(self.project.revision_deadline), new_date)
        # No reminders are due for the new deadline yet
        self.assertEqual(self.project.revision_reminders_sent, 0)
        self.assertTrue(InternalNote.objects.filter(project=self.project, content__contains='deadline changed'))
        self.assertEqual({e.to[0] for e in mail.outbox}, self.author_emails())

    def test_deadline_must_be_in_future(self):
        old_deadline = self.await_revisions(days_from_now(5)).revision_deadline
        self.client.login(username=EDITOR, password=PASSWORD)
        response = self.client.post(self.url(), {
            'extend_revision_deadline': '', 'revision_deadline': timezone.localdate().isoformat()})
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision_deadline, old_deadline)

    def test_other_user_cannot_extend_deadline(self):
        old_deadline = self.await_revisions(days_from_now(5)).revision_deadline
        self.client.login(username='amitupreti', password=PASSWORD)
        new_date = timezone.localdate() + datetime.timedelta(days=60)
        self.client.post(self.url(), {'extend_revision_deadline': '', 'revision_deadline': new_date.isoformat()})
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision_deadline, old_deadline)

    def test_managing_editor_can_reopen_archived_project(self):
        self.await_revisions(days_from_now(-1))
        self.run_command()
        mail.outbox.clear()
        user = User.objects.get(username='amitupreti')
        group, _ = Group.objects.get_or_create(name='Managing Editor')
        group.permissions.add(Permission.objects.get(codename='can_archive_project'))
        user.groups.add(group)
        self.client.login(username='amitupreti', password=PASSWORD)

        response = self.client.get(self.url())
        self.assertContains(response, 'Reopen for Revisions')

        new_date = timezone.localdate() + datetime.timedelta(days=30)
        self.client.post(self.url(), {'reopen_for_revisions': '', 'revision_deadline': new_date.isoformat()})
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)
        self.assertEqual(timezone.localdate(self.project.revision_deadline), new_date)
        self.assertIsNone(self.project.archive_reason)
        self.assertIn('reopened', mail.outbox[0].subject)

    def test_rejected_project_cannot_be_reopened(self):
        self.project.reject()
        self.client.login(username=EDITOR, password=PASSWORD)
        new_date = timezone.localdate() + datetime.timedelta(days=30)
        self.client.post(self.url(), {'reopen_for_revisions': '', 'revision_deadline': new_date.isoformat()})
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.ARCHIVED)


class TestExistingProjectBackfill(RevisionDeadlineTestMixin):
    def test_existing_projects_get_grace_period(self):
        migration = importlib.import_module('project.migrations.0117_revision_deadline')
        recent = self.await_revisions(days_from_now(1))
        ActiveProject.objects.filter(pk=recent.pk).update(
            revision_deadline=None, revision_request_datetime=days_from_now(-30))

        migration.set_existing_revision_deadlines(apps, None)
        recent.refresh_from_db()
        # 180 days after the request is later than 90 days from now
        self.assertAlmostEqual(
            recent.revision_deadline, days_from_now(150), delta=datetime.timedelta(minutes=5))

        ActiveProject.objects.filter(pk=recent.pk).update(
            revision_deadline=None, revision_request_datetime=days_from_now(-400))
        migration.set_existing_revision_deadlines(apps, None)
        recent.refresh_from_db()
        self.assertAlmostEqual(
            recent.revision_deadline, days_from_now(90), delta=datetime.timedelta(minutes=5))
