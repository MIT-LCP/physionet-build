from django.db import models

from physionet.enums import LogCategory
from project.managers.log import AccessLogQuerySet, GCPLogQuerySet
from project.modelcomponents.publishedproject import PublishedProject
from user.models import User


class Log(models.Model):
    """Base model for different log types"""
    category = models.CharField(max_length=64, choices=LogCategory.choices(), editable=False)
    project = models.ForeignKey(PublishedProject, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    data = models.TextField(max_length=512)
    count = models.PositiveIntegerField(default=1)
    creation_datetime = models.DateTimeField(auto_now_add=True)
    last_access_datetime = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'[{self.category}] {self.project} - {self.user}'


class AccessLog(Log):
    """Proxy model for access logs""" 
    objects = AccessLogQuerySet.as_manager()

    class Meta:
        proxy = True


class GCPLog(Log):
    """Proxy model for GCP logs"""
    objects = GCPLogQuerySet.as_manager()

    class Meta:
        proxy = True


