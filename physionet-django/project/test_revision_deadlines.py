import datetime
import importlib
from io import StringIO
from unittest import mock

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from notification.models import Notification
import notification.utility as notification_utility
from project.models import ActiveProject, ArchiveReason, InternalNote, RevisionType, SubmissionStatus
from user.models import User
from user.test_views import TestMixin

PROJECT_TITLE = 'Demo software for parsing clinical notes'
EDITOR = 'tompollard'
PASSWORD = 'Tester11!'


def days_from_now(days):
    return timezone.now() + datetime.timedelta(days=days)


def local_datetime(*args):
    """An aware datetime in the site time zone."""
    return timezone.make_aware(datetime.datetime(*args))


def end_of_local_day(dt):
    return timezone.make_aware(datetime.datetime.combine(timezone.localdate(dt), datetime.time(23, 59, 59)))


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
        now = local_datetime(2026, 3, 2, 8, 0)
        self.project.request_revisions(RevisionType.MINOR, now)
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)
        # The deadline is the end of the day, 90 days later
        self.assertEqual(self.project.revision_deadline, local_datetime(2026, 5, 31, 23, 59, 59))
        self.assertEqual(self.project.revision_reminders_sent, 0)

        self.project.request_revisions(RevisionType.MAJOR, now)
        self.assertEqual(self.project.revision_deadline, local_datetime(2026, 8, 29, 23, 59, 59))

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

    def test_deadline_is_paused_while_on_hold(self):
        start = local_datetime(2026, 3, 2, 8, 0)
        with mock.patch('django.utils.timezone.now', return_value=start):
            self.await_revisions(local_datetime(2026, 3, 12, 23, 59, 59))
            self.project.place_on_hold()

        # 20 days on hold: the deadline passes while the project is on hold
        with mock.patch('django.utils.timezone.now', return_value=start + datetime.timedelta(days=20)):
            self.run_command()
            self.project.refresh_from_db()
            self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)
            self.assertTrue(self.project.remove_from_hold())
            self.project.refresh_from_db()
            # The deadline moves later by the 20 days on hold
            self.assertEqual(self.project.revision_deadline, local_datetime(2026, 4, 1, 23, 59, 59))
            self.assertFalse(self.project.is_on_hold)
            self.assertIsNone(self.project.on_hold_datetime)
            self.run_command()
            self.project.refresh_from_db()
            self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)

    def test_hold_before_revisions_only_pauses_from_revision_request(self):
        start = local_datetime(2026, 3, 2, 8, 0)
        with mock.patch('django.utils.timezone.now', return_value=start):
            self.project.place_on_hold()
        with mock.patch('django.utils.timezone.now', return_value=start + datetime.timedelta(days=10)):
            self.project.refresh_from_db()
            self.project.request_revisions(RevisionType.MINOR)
            self.project.save()
        deadline = self.project.revision_deadline
        with mock.patch('django.utils.timezone.now', return_value=start + datetime.timedelta(days=15)):
            self.project.remove_from_hold()
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision_deadline, end_of_local_day(deadline + datetime.timedelta(days=5)))

    @override_settings(REVISION_DEADLINE_DAYS_MINOR=90, REVISION_DEADLINE_DAYS_MAJOR=180)
    def test_projects_without_deadline_get_one(self):
        # For example, revisions requested by the previous version of the
        # code after migration 0117 had run
        self.await_revisions(days_from_now(-1))
        request = local_datetime(2026, 3, 2, 8, 0)
        ActiveProject.objects.filter(pk=self.project.pk).update(
            revision_deadline=None, revision_request_datetime=request)

        with mock.patch('django.utils.timezone.now', return_value=request + datetime.timedelta(hours=1)):
            self.run_command()
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)
        # 180 days after the request is later than 90 days from now
        self.assertEqual(self.project.revision_deadline, local_datetime(2026, 8, 29, 23, 59, 59))
        self.assertEqual(len(mail.outbox), 0)

        # The project is archived once the new deadline has passed
        with mock.patch('django.utils.timezone.now', return_value=request + datetime.timedelta(days=400)):
            self.run_command()
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.ARCHIVED)

    @override_settings(REVISION_DEADLINE_DAYS_MINOR=90)
    def test_deadline_lasts_until_end_of_day(self):
        decision = local_datetime(2026, 3, 2, 8, 0)
        self.project.request_revisions(RevisionType.MINOR, decision)
        self.project.save()
        deadline_day = datetime.date(2026, 5, 31)
        self.assertEqual(timezone.localdate(self.project.revision_deadline), deadline_day)

        # The daily run on the deadline day, after the time of the decision,
        # does not archive the project
        with mock.patch('django.utils.timezone.now', return_value=local_datetime(2026, 5, 31, 9, 15)):
            self.run_command()
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.NEEDS_RESUBMISSION)

        # The run on the next day does
        with mock.patch('django.utils.timezone.now', return_value=local_datetime(2026, 6, 1, 9, 15)):
            self.run_command()
        self.project.refresh_from_db()
        self.assertEqual(self.project.submission_status, SubmissionStatus.ARCHIVED)

    def test_failed_reminder_is_retried(self):
        self.await_revisions(days_from_now(60))
        ActiveProject.objects.filter(pk=self.project.pk).update(revision_deadline=days_from_now(29))
        with mock.patch('notification.utility.send_mail', side_effect=OSError('SMTP down')):
            self.run_command()
        self.project.refresh_from_db()
        # Nobody was emailed, so the reminder is still due
        self.assertEqual(self.project.revision_reminders_sent, 0)
        self.assertFalse(Notification.objects.filter(message__startswith='Reminder - revisions due'))

        self.run_command()
        self.assertEqual({e.to[0] for e in mail.outbox}, self.author_emails())
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision_reminders_sent, 1)
        self.assertEqual(Notification.objects.filter(message__startswith='Reminder - revisions due').count(),
                         self.project.authors.count())

    def test_partly_failed_reminder_is_retried_only_for_failed_authors(self):
        self.await_revisions(days_from_now(60))
        ActiveProject.objects.filter(pk=self.project.pk).update(revision_deadline=days_from_now(29))
        emails = sorted(self.author_emails())
        self.assertGreater(len(emails), 1)
        failing = emails[0]
        real_send_mail = notification_utility.send_mail

        def send_mail(subject, body, sender, recipients, **kwargs):
            if recipients == [failing]:
                raise OSError('Mailbox unavailable')
            return real_send_mail(subject, body, sender, recipients, **kwargs)

        with mock.patch('notification.utility.send_mail', side_effect=send_mail):
            self.run_command()
        self.assertEqual({e.to[0] for e in mail.outbox}, set(emails[1:]))
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision_reminders_sent, 1)
        self.assertEqual(self.project.revision_reminder_retry_emails, [failing])

        # The next run emails only the author who missed the reminder
        mail.outbox.clear()
        self.run_command()
        self.assertEqual([e.to for e in mail.outbox], [[failing]])
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision_reminder_retry_emails, [])
        # In-app notifications are created once
        self.assertEqual(Notification.objects.filter(message__startswith='Reminder - revisions due').count(),
                         self.project.authors.count())

        # And nothing more is sent
        mail.outbox.clear()
        self.run_command()
        self.assertEqual(len(mail.outbox), 0)

    def test_reminder_without_revision_request_date(self):
        self.await_revisions(days_from_now(60))
        ActiveProject.objects.filter(pk=self.project.pk).update(
            revision_deadline=days_from_now(29), revision_request_datetime=None)
        self.run_command()
        body = ' '.join(mail.outbox[0].body.split())
        self.assertIn(f'revisions were requested for your project "{self.project.title}", and', body)

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


class TestRemoveFromHoldView(RevisionDeadlineTestMixin):
    def test_authors_told_of_new_deadline(self):
        self.await_revisions(days_from_now(-1))
        self.project.place_on_hold()
        ActiveProject.objects.filter(pk=self.project.pk).update(on_hold_datetime=days_from_now(-10))
        self.client.login(username=EDITOR, password=PASSWORD)
        self.client.post(reverse('project_on_hold', args=(self.project.slug,)), {'remove_from_hold': ''})
        self.project.refresh_from_db()
        self.assertFalse(self.project.is_on_hold)
        self.assertGreater(self.project.revision_deadline, timezone.now() + datetime.timedelta(days=8))
        self.assertTrue(InternalNote.objects.filter(project=self.project, content__startswith='Removed from hold'))
        self.assertEqual({e.to[0] for e in mail.outbox}, self.author_emails())

    def test_no_change_for_other_stages(self):
        self.project.place_on_hold()
        self.client.login(username=EDITOR, password=PASSWORD)
        self.client.post(reverse('project_on_hold', args=(self.project.slug,)), {'remove_from_hold': ''})
        self.project.refresh_from_db()
        self.assertFalse(self.project.is_on_hold)
        self.assertIsNone(self.project.revision_deadline)
        self.assertEqual(len(mail.outbox), 0)


class TestManagingEditorPermissionMigration(TestMixin):
    def test_permission_granted_regardless_of_group_name_case(self):
        migration = importlib.import_module('project.migrations.0118_managing_editor_archive_permission')
        permission = Permission.objects.get(codename='can_archive_project')
        Group.objects.filter(name__iexact='managing editor').delete()
        group = Group.objects.create(name='managing editor')
        self.assertFalse(group.permissions.filter(pk=permission.pk).exists())

        migration.grant_archive_permission(apps, None)
        self.assertTrue(group.permissions.filter(pk=permission.pk).exists())


class TestExistingProjectBackfill(RevisionDeadlineTestMixin):
    def test_existing_projects_get_grace_period(self):
        migration = importlib.import_module('project.migrations.0117_revision_deadline')
        recent = self.await_revisions(days_from_now(1))
        ActiveProject.objects.filter(pk=recent.pk).update(
            revision_deadline=None, revision_request_datetime=days_from_now(-30))

        migration.set_existing_revision_deadlines(apps, None)
        recent.refresh_from_db()
        # 180 days after the request is later than 90 days from now. The
        # deadline is the end of that day.
        self.assertEqual(recent.revision_deadline, end_of_local_day(days_from_now(150)))

        ActiveProject.objects.filter(pk=recent.pk).update(
            revision_deadline=None, revision_request_datetime=days_from_now(-400))
        migration.set_existing_revision_deadlines(apps, None)
        recent.refresh_from_db()
        self.assertEqual(recent.revision_deadline, end_of_local_day(days_from_now(90)))

        # The command's fallback for projects without a deadline matches
        self.assertEqual(recent.fallback_revision_deadline(), recent.revision_deadline)
