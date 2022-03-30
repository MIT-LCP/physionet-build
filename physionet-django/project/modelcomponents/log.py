from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from physionet.enums import LogCategory
from project.managers.log import AccessLogQuerySet, GCPLogQuerySet, AccessLogManager, GCPLogManager


class Log(models.Model):
    """Base model for different log types"""
    category = models.CharField(max_length=64, choices=LogCategory.choices(), editable=False)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')
    user = models.ForeignKey('user.User', on_delete=models.CASCADE, related_name='logs')
    data = models.TextField(max_length=512)
    count = models.PositiveIntegerField(default=1)
    creation_datetime = models.DateTimeField(auto_now_add=True)
    last_access_datetime = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f'[{self.category}] {self.project} - {self.user}'

    def get_data(self):
        return self.data.split(';')


class AccessLog(Log):
    """Proxy model for access logs"""
    objects = AccessLogManager.from_queryset(AccessLogQuerySet)()

    class Meta:
        default_permissions = ()
        proxy = True


class GCPLog(Log):
    """Proxy model for GCP logs"""
    objects = GCPLogManager.from_queryset(GCPLogQuerySet)()

    class Meta:
        default_permissions = ()
        proxy = True
