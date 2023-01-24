from logging import getLogger
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, Group
from django.contrib.auth.admin import GroupAdmin as DefaultGroupAdmin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.db.models.signals import post_save
from django.dispatch import receiver

from user import models

from user import forms

logger = getLogger('admin')

class UserAdmin(DefaultUserAdmin):
    """
    The class for enabling the django admin interface to
    interact with the custom User.

    Many fields are inherited from the built-in django
    UserAdmin. We have to override fields to make this custom
    admin compatible with our custom model.
    """

    # The forms to add and change user instances in the admin panel
    form = forms.UserChangeForm
    add_form = forms.RegistrationForm

    # The fields to be used in displaying the User model.
    list_display = ('email', 'is_active', 'is_admin', 'profile')
    # Filtering options when displaying objects
    list_filter = ('is_admin',)

    # Controls the layout of 'add' and 'change' pages.
    # List of tuple pairs. Element 1 is name, 2 is dict of field options.
    # For editing users
    fieldsets = (
        (None, {
            'fields': (
                'password',
                'groups',
                'user_permissions',
                'is_admin',
                'is_active',
                'is_superuser',
                'last_login',
                'join_date'
            )
        }),
    )

    # add_fieldsets is not a standard ModelAdmin attribute. UserAdmin
    # overrides get_fieldsets to use this attribute when creating a user.
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_admin')}
        ),
    )

    search_fields = ('email',)
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)
    readonly_fields = ('join_date',)

    def render_change_form(self, request, context, *args, **kwargs):
        context['adminform'].form.fields['user_permissions'].queryset = Permission.objects.exclude(
            content_type__app_label__in=('auth', 'admin', 'background_task', 'contenttypes', 'sessions', 'sites')
        )
        return super().render_change_form(request, context, *args, **kwargs)


class GroupAdmin(DefaultGroupAdmin):
    def render_change_form(self, request, context, *args, **kwargs):
        context['adminform'].form.fields['permissions'].queryset = Permission.objects.exclude(
            content_type__app_label__in=('auth', 'admin', 'background_task', 'contenttypes', 'sessions', 'sites')
        )
        return super().render_change_form(request, context, *args, **kwargs)


@receiver(post_save, sender=LogEntry)
def log_admin_panel_activity(sender, **kwargs):
    """
    Logs Django Admin Panel activity via the configured logger
    """
    log_entry_instance = kwargs['instance']
    logger.info(log_entry_instance, extra={'user': log_entry_instance.user.username})


# Unregister and register Group with new GroupAdmin
admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)

# Register the custom User model with the custom UserAdmin model
admin.site.register(models.User, UserAdmin)
admin.site.register(models.Profile)
admin.site.register(models.AssociatedEmail)

admin.site.register(models.LegacyCredential)
admin.site.register(models.CredentialApplication)

admin.site.register(models.TrainingType)
admin.site.register(models.Training)
admin.site.register(models.Question)
admin.site.register(models.TrainingQuestion)
admin.site.register(models.TrainingRegex)
