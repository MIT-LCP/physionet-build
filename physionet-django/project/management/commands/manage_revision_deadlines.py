"""
Remind authors of upcoming revision deadlines, and archive projects that
were not resubmitted by their deadline.

This command is intended to be run periodically (e.g. daily, by cron).

Projects that are on hold are not reminded or archived. Their deadline is
paused: when they are taken off hold, it is moved later by the time spent
on hold (see ActiveProject.remove_from_hold).
"""
import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

import notification.utility as notification
from project.models import ActiveProject, ArchiveReason, SubmissionStatus

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send revision deadline reminders and archive projects whose revision deadline has passed.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be done without changing anything or sending email.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        assigned = self.assign_missing_deadlines(now, dry_run)

        projects = ActiveProject.objects.filter(
            submission_status=SubmissionStatus.NEEDS_RESUBMISSION,
            is_on_hold=False,
            revision_deadline__isnull=False,
        ).order_by('revision_deadline')

        archived = reminded = retried = 0
        for project in projects:
            if project.revision_deadline <= now:
                if self.archive(project, dry_run):
                    archived += 1
                continue
            reminders_due = ActiveProject.revision_reminders_due(project.revision_deadline, now)
            if reminders_due > project.revision_reminders_sent:
                if self.remind(project, reminders_due, dry_run):
                    reminded += 1
            elif project.revision_reminder_retry_emails:
                if self.retry_reminder(project, dry_run):
                    retried += 1

        prefix = '[dry run] ' if dry_run else ''
        self.stdout.write(f'{prefix}Assigned {assigned} missing deadline(s); archived {archived} project(s); '
                          f'reminded authors of {reminded} project(s); retried reminders for {retried} project(s).')

    def assign_missing_deadlines(self, now, dry_run):
        """
        Give a deadline to projects awaiting revisions that have none.

        This covers projects that entered revisions without a deadline, for
        example through a decision made by the previous version of the code
        while this version was being deployed.
        """
        assigned = 0
        projects = ActiveProject.objects.filter(
            submission_status=SubmissionStatus.NEEDS_RESUBMISSION,
            revision_deadline__isnull=True,
        )
        for project in projects:
            deadline = project.fallback_revision_deadline(now)
            if dry_run:
                self.stdout.write(f'Would set the revision deadline of {project.slug} to {deadline:%Y-%m-%d}')
                assigned += 1
                continue
            updated = ActiveProject.objects.filter(
                pk=project.pk,
                submission_status=SubmissionStatus.NEEDS_RESUBMISSION,
                revision_deadline__isnull=True,
            ).update(
                revision_deadline=deadline,
                revision_reminders_sent=ActiveProject.revision_reminders_due(deadline, now),
                revision_reminder_retry_emails=[],
            )
            if updated:
                LOGGER.info('Set missing revision deadline of project %s to %s', project.slug, deadline)
                assigned += 1
        return assigned

    def archive(self, project, dry_run):
        """
        Archive a project whose revision deadline has passed, and notify the
        authors and editor. Returns True if the project was archived.
        """
        deadline = project.revision_deadline
        if dry_run:
            self.stdout.write(f'Would archive {project.slug} (deadline {deadline:%Y-%m-%d})')
            return True

        with transaction.atomic():
            # Lock the row and check again, in case the project was resubmitted
            # or the deadline extended since it was selected.
            project = ActiveProject.objects.select_for_update().get(pk=project.pk)
            if (project.submission_status != SubmissionStatus.NEEDS_RESUBMISSION
                    or project.is_on_hold
                    or not project.revision_deadline
                    or project.revision_deadline > timezone.now()):
                return False
            project.archive(archive_reason=ArchiveReason.REVISION_DEADLINE_PASSED)

        LOGGER.info('Archived project %s: revision deadline %s passed', project.slug, deadline)
        try:
            notification.revision_deadline_passed_notify(project, deadline)
        except Exception:
            LOGGER.exception('Could not send revision deadline notification for project %s', project.slug)
        return True

    def remind(self, project, reminders_due, dry_run):
        """
        Send a deadline reminder to the authors of a project. Returns True if
        the reminder was sent to at least one author.

        If no author could be emailed, the reminder is released so that the
        next run tries again. If only some could, the others are recorded in
        revision_reminder_retry_emails and retried on later runs, so that
        authors who received the reminder do not get it twice.
        """
        if dry_run:
            self.stdout.write(f'Would remind authors of {project.slug} '
                              f'(deadline {project.revision_deadline:%Y-%m-%d})')
            return True

        # Claim the reminder with a conditional update, so that it is sent
        # only once even if the command runs twice at the same time, and not
        # at all if the deadline was changed in the meantime.
        previous = project.revision_reminders_sent
        claimed = ActiveProject.objects.filter(
            pk=project.pk,
            submission_status=SubmissionStatus.NEEDS_RESUBMISSION,
            revision_deadline=project.revision_deadline,
            revision_reminders_sent=previous,
        ).update(revision_reminders_sent=reminders_due, revision_reminder_retry_emails=[])
        if not claimed:
            return False
        project.revision_reminders_sent = reminders_due

        recipients = {email for email, _ in project.author_contact_info()}
        failed = notification.revision_deadline_reminder_notify(project)

        if recipients and failed >= recipients:
            # Nobody was emailed: release the claim so the next run retries.
            ActiveProject.objects.filter(
                pk=project.pk,
                revision_deadline=project.revision_deadline,
                revision_reminders_sent=reminders_due,
            ).update(revision_reminders_sent=previous)
            LOGGER.error('Revision deadline reminder for project %s could not be sent; it will be retried',
                         project.slug)
            return False

        ActiveProject.objects.filter(
            pk=project.pk,
            revision_deadline=project.revision_deadline,
            revision_reminders_sent=reminders_due,
        ).update(latest_reminder=timezone.now(), revision_reminder_retry_emails=sorted(failed))
        notification.revision_deadline_reminder_in_app_notify(project)
        if failed:
            LOGGER.error('Revision deadline reminder for project %s could not be sent to %s; it will be retried',
                         project.slug, ', '.join(sorted(failed)))
        else:
            LOGGER.info('Sent revision deadline reminder for project %s', project.slug)
        return True

    def retry_reminder(self, project, dry_run):
        """
        Retry the latest deadline reminder for authors who did not receive
        it. Returns True if it was sent to at least one of them.
        """
        if dry_run:
            self.stdout.write(f'Would retry the reminder for {project.slug} to '
                              f'{", ".join(project.revision_reminder_retry_emails)}')
            return True

        with transaction.atomic():
            # Lock the row while taking the list, so that two runs cannot
            # retry the same authors.
            locked = ActiveProject.objects.select_for_update().get(pk=project.pk)
            pending = set(locked.revision_reminder_retry_emails or [])
            if (not pending
                    or locked.submission_status != SubmissionStatus.NEEDS_RESUBMISSION
                    or locked.revision_deadline != project.revision_deadline
                    or locked.revision_reminders_sent != project.revision_reminders_sent):
                return False
            locked.revision_reminder_retry_emails = []
            locked.save(update_fields=['revision_reminder_retry_emails'])

        failed = notification.revision_deadline_reminder_notify(locked, recipients=pending)
        # Authors who are no longer on the project are not emailed, and are
        # dropped from the list.
        current = {email for email, _ in locked.author_contact_info()}
        failed &= current
        if failed:
            ActiveProject.objects.filter(
                pk=project.pk,
                revision_deadline=project.revision_deadline,
                revision_reminders_sent=project.revision_reminders_sent,
            ).update(revision_reminder_retry_emails=sorted(failed))
            LOGGER.error('Revision deadline reminder for project %s could not be sent to %s; it will be retried',
                         project.slug, ', '.join(sorted(failed)))
        return len(failed) < len(pending & current)
