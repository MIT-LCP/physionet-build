from django.contrib import admin
from background_task.models_completed import CompletedTask

from background_task.models import Task


class TaskAdmin(admin.ModelAdmin):
    display_filter = ['verbose_name']
    list_display = ['verbose_name', 'task_params', 'run_at', 'priority',
        'attempts', 'has_error', 'locked_by', 'locked_by_pid_running', ]


class CompletedTaskAdmin(admin.ModelAdmin):
    display_filter = ['verbose_name']
    list_display = ['verbose_name', 'task_params', 'run_at', 'priority',
        'attempts', 'has_error', 'locked_by', 'locked_by_pid_running', ]

# Unregister the tasks to add the custom tasks to the amdin page
admin.site.unregister(Task)
admin.site.unregister(CompletedTask)

admin.site.register(Task, TaskAdmin)
admin.site.register(CompletedTask, CompletedTaskAdmin)
