import inspect
import json

from background_task.models import Task, task_failed, task_rescheduled
from django.dispatch import receiver

import notification.utility as notification

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
    a TaskProxy object), where one of the parameters to that function
    refers to a field in the given model ('pk', i.e., the model's
    primary key, by default.)

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


def get_associated_tasks(instance, *, read_only=None):
    """
    Find pending tasks associated with a model instance.

    This function returns an iterator whose members are 2-tuples
    (task, read_only).  task is a Task object; read_only is the flag
    passed to the associated_task decorator.

    If read_only is True, return only "read-only" tasks.  If read_only
    is False, return only "read-write" tasks.

    The order that tasks are returned is unspecified.  Note that if a
    particular task has multiple associations defined, that task may
    conceivably appear multiple times in the sequence.
    """

    model = type(instance)._meta.label

    # Consider all possible task_names that might be associated with
    # this object.
    for (task_name, param_info) in sorted(_model_tasks[model].items()):

        # If we are only interested in read-only tasks, skip checking
        # read-write parameters, and vice versa.
        if read_only is not None:
            param_info = [p for p in param_info if p[3] == read_only]
        if not param_info:
            continue

        # Scan all pending tasks with this task_name.
        tasks = Task.objects.filter(task_name=task_name)
        for task in tasks:
            # Parse the given task's arguments (stored in task_params
            # as a JSON string) and check whether they match the given
            # instance.
            (args, kwargs) = json.loads(task.task_params)
            for (field, param, param_index, ro_flag) in param_info:
                value = getattr(instance, field)
                try:
                    if value == args[param_index]:
                        yield (task, ro_flag)
                except (TypeError, IndexError):
                    pass
                try:
                    if value == kwargs[param]:
                        yield (task, ro_flag)
                except KeyError:
                    pass


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
