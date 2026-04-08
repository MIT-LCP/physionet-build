from background_task.models import Task
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction


class Command(BaseCommand):
    """
    Unlock all pending background tasks.

    When the django-background-tasks daemon starts running a task, the
    task is "locked" so that another daemon won't try to run it at the
    same time.  If the daemon is interrupted without completing the
    task, the task may never be "unlocked".

    Manually unlocking tasks is generally not desirable since it can
    result in multiple instances of the same task running (although as
    a rule, tasks should be designed to be idempotent and not to break
    if this happens.)

    This command is primarily intended to be invoked by systemd when
    starting or restarting the django-background-tasks daemon.
    """

    def handle(self, *args, **options):
        verbosity = options['verbosity']

        with transaction.atomic():
            tasks = Task.objects.filter(locked_by__isnull=False)
            for task in tasks:
                duration = timezone.now() - task.locked_at
                task.locked_at = None
                task.locked_by = None
                task.save(update_fields=['locked_at', 'locked_by'])
                if verbosity > 0:
                    self.stdout.write(
                        f'Unlocked task {task.pk} ({task.task_name}) '
                        f'which was started {duration} ago'
                    )
