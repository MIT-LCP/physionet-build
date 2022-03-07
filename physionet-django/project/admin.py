from background_task.models import Task
from background_task.models import CompletedTask
from ckeditor.fields import RichTextField
from ckeditor.widgets import CKEditorWidget
from django.contrib import admin
from django.db.models import CharField, TextField
from django.forms import Textarea, TextInput
from project import models
from project.modelcomponents.log import AccessLog, GCPLog


class LicenseAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}


class LegacyProjectModelAdmin(admin.ModelAdmin):
    formfield_overrides = {
        CharField: {'widget': TextInput(attrs={'size':'200'})},
        TextField: {'widget': Textarea(attrs={'rows':4, 'cols':40})},
    }


class PublishedPublicationInline(admin.TabularInline):
    """
    Used to add/edit the publication of a published project
    """
    model = models.PublishedPublication
    max_num = 1


class PublishedAuthorInline(admin.StackedInline):
    """
    Used to add/edit the authors of a published project
    """
    model = models.PublishedAuthor


class ContactInline(admin.TabularInline):
    """
    Used to add/edit the contact of a published project
    """
    model = models.Contact


class PublishedProjectAdmin(admin.ModelAdmin):
    fields = ('title', 'abstract', 'background', 'methods',
        'content_description', 'usage_notes', 'installation',
        'acknowledgements', 'conflicts_of_interest', 'release_notes',
        'short_description', 'project_home_page', 'doi')

    readonly_fields = ('publish_datetime',)
    inlines = [PublishedPublicationInline, ContactInline,
        PublishedAuthorInline]
    list_display = ('title', 'version', 'is_legacy', 'publish_datetime')


class PublishedAffiliationInline(admin.TabularInline):
    """
    Used to add/edit affiliations of published authors
    """
    model = models.PublishedAffiliation
    max_num = 3


class PublishedAuthorAdmin(admin.ModelAdmin):
    list_display = ('project', 'user')
    inlines = [PublishedAffiliationInline]

class TaskAdmin(admin.ModelAdmin):
    display_filter = ['verbose_name']
    list_display = ['verbose_name', 'task_params', 'run_at', 'priority',
        'attempts', 'has_error', 'locked_by', 'locked_by_pid_running', ]


class CompletedTaskAdmin(admin.ModelAdmin):
    display_filter = ['verbose_name']
    list_display = ['verbose_name', 'task_params', 'run_at', 'priority',
        'attempts', 'has_error', 'locked_by', 'locked_by_pid_running', ]


class LogAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user').prefetch_related('project')


# Unregister the tasks to add the custom tasks to the amdin page
admin.site.unregister(Task)
admin.site.unregister(CompletedTask)


admin.site.register(models.ActiveProject)
admin.site.register(models.AuthorInvitation)
admin.site.register(models.CoreProject)
admin.site.register(models.LegacyProject, LegacyProjectModelAdmin)
admin.site.register(models.License, LicenseAdmin)
admin.site.register(models.PublishedAuthor, PublishedAuthorAdmin)
admin.site.register(models.PublishedProject, PublishedProjectAdmin)
admin.site.register(models.PublishedTopic)
admin.site.register(models.ProgrammingLanguage)
admin.site.register(models.Reference)
admin.site.register(models.Topic)
admin.site.register(models.Affiliation)
admin.site.register(models.ArchivedProject)
admin.site.register(models.Contact)
admin.site.register(models.ContentType)
admin.site.register(models.CopyeditLog)
admin.site.register(models.DUASignature)
admin.site.register(models.EditLog)
admin.site.register(models.Publication)
admin.site.register(models.PublishedAffiliation)
admin.site.register(models.PublishedPublication)
admin.site.register(models.PublishedReference)
admin.site.register(models.StorageRequest)
admin.site.register(models.GCP)
admin.site.register(AccessLog, LogAdmin)
admin.site.register(GCPLog, LogAdmin)

# Add the custom tasks to the admin page
admin.site.register(Task, TaskAdmin)
admin.site.register(CompletedTask, CompletedTaskAdmin)
