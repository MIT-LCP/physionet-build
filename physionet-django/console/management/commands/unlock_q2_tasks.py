from django.core.management.base import BaseCommand
from django.utils import timezone

from django_q.models import OrmQ


class Command(BaseCommand):
    """
    Unlock all pending django-q2 tasks.

    When the django-q2 cluster dequeues a task, it sets the OrmQ
    row's lock field to now + retry (which can be hundreds of years
    with a very large retry setting).  If the cluster is interrupted
    without completing the task, the lock persists and the task is
    never re-dequeued.

    This command resets all OrmQ locks to now, making every pending
    task eligible for dequeuing again.

    This command is primarily intended to be invoked by systemd as
    ExecStartPre when starting or restarting the django-q2 daemon.
    """

    def handle(self, *args, **options):
        verbosity = options['verbosity']
        now = timezone.now()
        locked = OrmQ.objects.filter(lock__gt=now)
        count = locked.update(lock=now)
        if verbosity > 0:
            self.stdout.write(f'Unlocked {count} pending task(s)')
