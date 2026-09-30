from django import forms
from django.conf import settings
from django.contrib import admin
from tinymce.widgets import AdminTinyMCE

from notification import models


class NewsAdminForm(forms.ModelForm):
    class Meta:
        model = models.News
        fields = '__all__'
        widgets = {
            'content': AdminTinyMCE(mce_attrs=settings.TINYMCE_NEWS_CONFIG),
        }


@admin.register(models.News)
class NewsAdmin(admin.ModelAdmin):
    form = NewsAdminForm


@admin.register(models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'message', 'is_read', 'created_datetime')
    list_filter = ('is_read', 'notification_type', 'created_datetime')
    search_fields = ('recipient__username', 'recipient__email', 'message')
    raw_id_fields = ('recipient', 'actor')
