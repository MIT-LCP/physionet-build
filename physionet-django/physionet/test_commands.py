from django.core.management import call_command
from django.test import TestCase


class TestBackgroundTasks(TestCase):
    def test_process_tasks_command(self):
        """
        Check that we can run the 'process_tasks' command.

        This tests the legacy django-background-tasks system which is
        still active for draining any remaining tasks.
        """
        # There are no tasks in the demo database, so this command
        # shouldn't do anything.  However, process_tasks may fail if
        # installed apps can't be imported
        # (https://github.com/MIT-LCP/physionet-build/issues/2357)
        call_command('process_tasks', duration=1)


class TestDjangoQ2(TestCase):
    def test_qinfo_command(self):
        """
        Check that we can run the 'qinfo' command.

        This verifies that django-q2 is properly configured and that
        all installed apps can be imported.
        """
        call_command('qinfo')
