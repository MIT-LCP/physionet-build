import importlib
import inspect
import json
import logging
from hashlib import sha1

from background_task.models import Task, task_failed, task_rescheduled
from django.conf import settings
from django_q.models import OrmQ
from django_q.signing import SignedPackage
from django_q.tasks import async_task
from django.dispatch import receiver

import notification.utility as notification

logger = logging.getLogger(__name__)

_model_tasks = {}


def register_associated_task(task_name, model, param, param_index, *,
                             read_only=False, field='pk'):
    """
    Associate a background task with a model.

    One of the (positional and/or keyword) parameters to the task
    should refer to a field in the given model.

    - model is either a Model class or its label.
    - field is the name of a field defined in that class.
    - task_name is the name of a background task.
    - param is the name of the task parameter that corresponds to the
      given model field.
    - param_index is the index of the parameter (or None, if the
      parameter is keyword-only.)
    - read_only is true if the task is "read-only".

    This allows get_tasks() to identify tasks that are associated with
    a particular model instance.  Note that a single task name may
    have multiple (read-only and/or read-write) associations for
    different function parameters.
    """
    if not isinstance(model, str):
        model = model._meta.label
    task_info = _model_tasks.setdefault(model, {})
    param_info = task_info.setdefault(task_name, [])
    param_info.append((field, param, param_index, read_only))


def associated_task(model, param, *, read_only=False, field='pk'):
    """
    Decorator for tasks that are associated with model instances.

    The decorated function should be a background task function (i.e.,
    a TaskProxy object from @background()), where one of the
    parameters to that function refers to a field in the given model
    ('pk', i.e., the model's primary key, by default.)

    - model is either a Model class or its label.
    - field is the name of a field defined in that class.
    - param is the name of a parameter of the decorated function.
    - read_only is True if the task is "read-only".

    This allows get_tasks() to identify tasks that are associated with
    a particular model instance.

    Conceptually, this should be regarded as an advisory lock on the
    object, in that multiple "read-only" tasks may be invoked in
    parallel, but callers should not invoke any "read-write" task
    while another task is pending.  This is NOT ENFORCED in any way;
    indeed, there is nothing preventing the object itself from being
    deleted before the task has an opportunity to run.

    This decorator may be used multiple times to define associations
    for multiple function parameters.

    Example:

      @associated_task(PublishedProject, 'project_id')
      @background()
      def my_function(project_id, foo, bar):
          project = PublishedProject.objects.get(id=project_id)
          do_stuff(project, foo, bar)
    """
    def decorate(task_proxy):
        task_name = task_proxy.name
        function = task_proxy.task_function

        # Store task_name on the proxy so callers can use
        # task_proxy.task_name (consistent with django-q2 conventions)
        task_proxy.task_name = task_name

        # Determine index of the given parameter (so that we can
        # identify task instances regardless of whether they are
        # invoked in positional or keyword style)
        argspec = inspect.getfullargspec(function)
        try:
            param_index = argspec.args.index(param)
        except ValueError:
            param_index = None
        if param_index is None and param not in argspec.kwonlyargs:
            raise Exception(
                'Task {} does not have a parameter named {}'.format(
                    task_name, param))

        register_associated_task(task_name=task_name,
                                 param=param, param_index=param_index,
                                 model=model, field=field,
                                 read_only=read_only)

        # task_proxy object itself is not modified
        return task_proxy
    return decorate


def _run_task(func_name, *args, **kwargs):
    """
    Resolve a task function by its dotted path and execute it.

    This is used as the entry point for django-q2 async_task() calls.
    The indirection avoids pickling issues with functions wrapped by
    @background() (whose module-level name is a TaskProxy, not the
    underlying function).
    """
    module_path, attr_name = func_name.rsplit('.', 1)
    module = importlib.import_module(module_path)
    func = getattr(module, attr_name)
    # Unwrap @background() TaskProxy to get the real function
    if hasattr(func, 'task_function'):
        func = func.task_function
    return func(*args, **kwargs)


class _TaskInfo:
    """Simple wrapper to expose task_name and a string representation."""
    def __init__(self, task_name, args, kwargs):
        self.task_name = task_name
        self.args = args
        self.kwargs = kwargs

    def __str__(self):
        return f'{self.task_name}({self.args}, {self.kwargs})'


def _unpack_ormq(ormq_obj):
    """
    Extract (func, args, kwargs) from an OrmQ entry.

    django-q2 stores the task payload as a signed/pickled dict.
    If the task was dispatched via _run_task, unwrap to get the
    real function name and arguments.
    """
    task_dict = SignedPackage.loads(ormq_obj.payload)
    func = task_dict.get('func', '')
    args = task_dict.get('args', ())
    kwargs = task_dict.get('kwargs', {})
    # Unwrap _run_task dispatcher: first arg is the real func name
    if func == _run_task and args:
        func = args[0]
        args = args[1:]
    return func, args, kwargs


def _match_params(args, kwargs, param_info, instance):
    """
    Check whether (args, kwargs) match the given instance for any of
    the parameter associations in param_info.  Yields ro_flag for each
    match.
    """
    for (field_name, param_name, param_index, ro_flag) in param_info:
        value = getattr(instance, field_name)
        matched = False
        try:
            if value == args[param_index]:
                matched = True
        except (TypeError, IndexError):
            pass
        try:
            if value == kwargs[param_name]:
                matched = True
        except KeyError:
            pass
        if matched:
            yield ro_flag


def get_associated_tasks(instance, *, read_only=None, name=None):
    """
    Find pending tasks associated with a model instance.

    This function checks both the legacy django-background-tasks queue
    (Task model) and the django-q2 queue (OrmQ model).

    This function returns an iterator whose members are 2-tuples
    (task_info, read_only).  task_info is a Task object (for legacy
    tasks) or a _TaskInfo object (for django-q2 tasks); read_only is
    the flag passed to the associated_task decorator.

    If read_only is True, return only "read-only" tasks.  If read_only
    is False, return only "read-write" tasks.

    The order that tasks are returned is unspecified.  Note that if a
    particular task has multiple associations defined, that task may
    conceivably appear multiple times in the sequence.
    """

    model = type(instance)._meta.label

    if name is None:
        # Consider all possible task_names that might be associated with
        # this object.
        task_names = sorted(_model_tasks[model].keys())
    else:
        task_names = [name]

    # Build a list of pending django-q2 tasks (func, args, kwargs)
    q2_pending = []
    for ormq_obj in OrmQ.objects.all():
        func, args, kwargs = _unpack_ormq(ormq_obj)
        if func:
            q2_pending.append((func, args, kwargs))

    for task_name in task_names:
        param_info = _model_tasks[model][task_name]

        # If we are only interested in read-only tasks, skip checking
        # read-write parameters, and vice versa.
        if read_only is not None:
            param_info = [p for p in param_info if p[3] == read_only]
        if not param_info:
            continue

        # Check legacy django-background-tasks queue
        legacy_tasks = Task.objects.filter(task_name=task_name)
        for task in legacy_tasks:
            (args, kwargs) = json.loads(task.task_params)
            for ro_flag in _match_params(args, kwargs, param_info, instance):
                yield (task, ro_flag)

        # Check django-q2 queue
        for (func, args, kwargs) in q2_pending:
            if func != task_name:
                continue
            for ro_flag in _match_params(args, kwargs, param_info, instance):
                task_info = _TaskInfo(task_name, args, kwargs)
                yield (task_info, ro_flag)


_RUN_TASK_FUNC_NAME = f'{__name__}._run_task'


def _unwrap_run_task(func, args):
    """
    If func is the _run_task dispatcher, extract the real function name
    and arguments.  Returns (func_name, real_args).
    """
    if func == _RUN_TASK_FUNC_NAME and args:
        return args[0], args[1:]
    return func, args


def task_completion_hook(task):
    """
    Hook called by django-q2 when a task finishes.

    Notifies admins when a task has failed.  With the effectively
    infinite retry (timeout/retry ~317 years), a failed task is
    acknowledged immediately (ack_failures=True) and never re-queued,
    so there is only ever one attempt per failure.
    """
    if not task.success:
        func_name, task_args = _unwrap_run_task(task.func, task.args)
        notification.task_failed_notify(
            name=task.name or '',
            attempts=task.attempt_count,
            last_error=task.result if isinstance(task.result, str) else str(task.result),
            date_time=task.stopped,
            task_name=func_name,
            task_params=str(task_args) if task_args else '',
        )


def enqueue_task(func, *args, task_name=None, remove_existing=False,
                 **kwargs):
    """
    Enqueue a function as a django-q2 async task.

    func should be a @background() TaskProxy or a plain function.  The
    actual function will be resolved and dispatched via django-q2's
    async_task.

    If remove_existing is True, delete any pending tasks with the same
    function name and arguments from both the legacy Task queue and the
    django-q2 OrmQ queue before enqueuing the new one.  This matches
    the legacy django-background-tasks behavior, which keyed on a hash
    of the task name and parameters.
    """
    # Resolve the dotted function name
    if hasattr(func, 'task_function'):
        # It's a @background() TaskProxy
        func_name = func.name
    else:
        func_name = f'{func.__module__}.{func.__qualname__}'

    if remove_existing:
        # Remove from legacy django-background-tasks queue.
        # The legacy system keyed on a hash of task_name + params,
        # so we replicate that by computing the same hash.
        task_params = json.dumps((args, kwargs), sort_keys=True)
        task_hash = sha1(
            f'{func_name}{task_params}'.encode('utf-8')
        ).hexdigest()
        Task.objects.filter(task_hash=task_hash).delete()

        # Remove from django-q2 queue (match on func name and args)
        for ormq_obj in OrmQ.objects.all():
            try:
                queued_func, queued_args, queued_kwargs = _unpack_ormq(ormq_obj)
            except Exception:
                logger.warning("Failed to unpack OrmQ entry %s",
                               ormq_obj.pk, exc_info=True)
                continue
            if (queued_func == func_name
                    and tuple(queued_args) == tuple(args)
                    and queued_kwargs == kwargs):
                ormq_obj.delete()

    # django-q2's Task.name is max_length=100.  If the label exceeds
    # that, save_task raises DataError and silently swallows it, which
    # means no Task row is created, the hook never fires, and admins
    # are never notified of failures.  Truncate to be safe.
    if task_name and len(task_name) > 100:
        task_name = task_name[:97] + '...'

    # Dispatch via _run_task to avoid pickling issues with
    # @background()-wrapped functions (TaskProxy objects).
    return async_task(
        _run_task, func_name, *args,
        task_name=task_name,
        hook='console.tasks.task_completion_hook',
        **kwargs,
    )


# Legacy django-background-tasks signal handlers.
# These handle notifications for tasks still draining through the old
# process_tasks daemon.  They can be removed once django-background-tasks
# is fully removed.

@receiver(task_rescheduled, sender=Task)
def task_rescheduled_handler(sender, **kwargs):
    """
    Notify the admins when a task has failed and rescheduled
    """
    name = kwargs['task'].verbose_name
    attempts = kwargs['task'].attempts
    last_error = kwargs['task'].last_error
    date_time = kwargs['task'].run_at
    task_name = kwargs['task'].task_name
    task_params = kwargs['task'].task_params
    notification.task_rescheduled_notify(name, attempts, last_error,
                                         date_time, task_name, task_params)


@receiver(task_failed, sender=Task)
def task_failed_handler(sender, **kwargs):
    """
    Notify the admins when a task has failed and removed from queue
    """
    name = kwargs['completed_task'].verbose_name
    attempts = kwargs['completed_task'].attempts
    last_error = kwargs['completed_task'].last_error
    date_time = kwargs['completed_task'].failed_at
    task_name = kwargs['completed_task'].task_name
    task_params = kwargs['completed_task'].task_params
    notification.task_failed_notify(name, attempts, last_error, date_time,
                                    task_name, task_params)
