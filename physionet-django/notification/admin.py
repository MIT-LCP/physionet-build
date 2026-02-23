from django.contrib import admin

from notification import models


admin.site.register(models.News)


@admin.register(models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'message', 'is_read', 'created_datetime')
    list_filter = ('is_read', 'notification_type', 'created_datetime')
    search_fields = ('recipient__username', 'recipient__email', 'message')
    raw_id_fields = ('recipient', 'actor')
