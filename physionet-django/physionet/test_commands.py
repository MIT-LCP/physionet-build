from django.core.management import call_command
from django.test import TestCase


class TestBackgroundTasks(TestCase):
    def test_process_tasks_command(self):
        """
        Check that we can run the 'process_tasks' command.
        """
        # There are no tasks in the demo database, so this command
        # shouldn't do anything.  However, process_tasks may fail if
        # installed apps can't be imported
        # (https://github.com/MIT-LCP/physionet-build/issues/2357)
        call_command('process_tasks', duration=1)
