"""
Remind authors of upcoming revision deadlines, and archive projects that
were not resubmitted by their deadline.

This command is intended to be run periodically (e.g. daily, by cron).
Projects that are on hold are skipped; their deadline still applies once
they are taken off hold, unless an editor extends it.
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
        projects = ActiveProject.objects.filter(
            submission_status=SubmissionStatus.NEEDS_RESUBMISSION,
            is_on_hold=False,
            revision_deadline__isnull=False,
        ).order_by('revision_deadline')

        archived = reminded = 0
        for project in projects:
            if project.revision_deadline <= now:
                if self.archive(project, dry_run):
                    archived += 1
                continue
            reminders_due = ActiveProject.revision_reminders_due(project.revision_deadline, now)
            if reminders_due > project.revision_reminders_sent:
                if self.remind(project, now, dry_run):
                    reminded += 1

        prefix = '[dry run] ' if dry_run else ''
        self.stdout.write(f'{prefix}Archived {archived} project(s); reminded authors of {reminded} project(s).')

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

    def remind(self, project, now, dry_run):
        """
        Send a deadline reminder to the authors of a project. Returns True if
        a reminder was sent.
        """
        due = ActiveProject.revision_reminders_due(project.revision_deadline, now)
        if dry_run:
            self.stdout.write(f'Would remind authors of {project.slug} '
                              f'(deadline {project.revision_deadline:%Y-%m-%d})')
            return True

        # Claim the reminder with a conditional update, so that it is sent
        # only once even if the command runs twice at the same time, and not
        # at all if the deadline was changed in the meantime.
        updated = ActiveProject.objects.filter(
            pk=project.pk,
            submission_status=SubmissionStatus.NEEDS_RESUBMISSION,
            revision_deadline=project.revision_deadline,
            revision_reminders_sent=project.revision_reminders_sent,
        ).update(revision_reminders_sent=due, latest_reminder=now)
        if not updated:
            return False

        project.revision_reminders_sent = due
        project.latest_reminder = now
        try:
            notification.revision_deadline_reminder_notify(project)
        except Exception:
            LOGGER.exception('Could not send revision deadline reminder for project %s', project.slug)
            return False
        LOGGER.info('Sent revision deadline reminder for project %s', project.slug)
        return True
