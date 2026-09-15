from multiprocessing import Queue, Value
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from console.tasks import _run_task, _unpack_ormq, enqueue_task
from django_q.models import OrmQ, Task as DjangoQTask
from django_q.monitor import monitor
from django_q.signing import SignedPackage
from django_q.worker import worker


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


def _test_task_for_q2(x, y):
    """A simple task function used by TestDjangoQ2AsyncPath."""
    return x + y


class TestDjangoQ2AsyncPath(TestCase):
    """
    Test the django-q2 async (non-sync) code path.

    The default test configuration uses Q_CLUSTER['sync'] = True,
    which means tasks execute inline and bypass the OrmQ queue,
    _run_task dispatcher, and _unpack_ormq unpacking.  This test
    class patches Conf.SYNC = False to exercise those paths in CI.
    """

    def _patch_sync_false(self):
        """Patch django-q2's cached Conf.SYNC to False."""
        return mock.patch('django_q.conf.Conf.SYNC', False)

    def test_enqueue_creates_ormq_row(self):
        """
        enqueue_task with sync=False should create an OrmQ entry
        that _unpack_ormq can correctly unpack.
        """
        self.assertEqual(OrmQ.objects.count(), 0)

        with self._patch_sync_false():
            enqueue_task(_test_task_for_q2, 3, 4, task_name='test add')

        self.assertEqual(OrmQ.objects.count(), 1)
        ormq_obj = OrmQ.objects.first()
        func, args, kwargs = _unpack_ormq(ormq_obj)
        func_name = (f'{_test_task_for_q2.__module__}'
                     f'.{_test_task_for_q2.__qualname__}')
        self.assertEqual(func, func_name)
        self.assertEqual(tuple(args), (3, 4))
        self.assertEqual(kwargs, {})

    def test_run_task_executes_function(self):
        """
        _run_task should resolve a dotted function path and execute it.
        """
        func_name = (f'{_test_task_for_q2.__module__}'
                     f'.{_test_task_for_q2.__qualname__}')
        result = _run_task(func_name, 10, 20)
        self.assertEqual(result, 30)

    def test_enqueue_and_process(self):
        """
        Enqueue a task with sync=False, then process it through the
        django-q2 worker to verify the full round-trip: enqueue_task →
        OrmQ → SignedPackage → _run_task → result.
        """
        with self._patch_sync_false():
            enqueue_task(_test_task_for_q2, 5, 7,
                         task_name='test round-trip')

        self.assertEqual(OrmQ.objects.count(), 1)
        ormq_obj = OrmQ.objects.first()

        # Manually drive the worker (same as django_q.tasks._sync)
        task_dict = SignedPackage.loads(ormq_obj.payload)
        task_queue = Queue()
        result_queue = Queue()
        task_queue.put(task_dict)
        task_queue.put("STOP")
        worker(task_queue, result_queue, Value("f", -1))
        result_queue.put("STOP")
        monitor(result_queue)
        task_queue.close()
        task_queue.join_thread()
        result_queue.close()
        result_queue.join_thread()

        # Verify the result was saved
        completed = DjangoQTask.objects.last()
        self.assertTrue(completed.success)
        self.assertEqual(completed.result, 12)
