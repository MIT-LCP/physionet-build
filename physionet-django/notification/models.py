import uuid

from django.db import models

from project.models import SafeHTMLField


class News(models.Model):
    """
    """
    title = models.CharField(max_length=100)
    content = SafeHTMLField()
    publish_datetime = models.DateTimeField(auto_now_add=True)
    url = models.URLField(default='', blank=True)
    project = models.ForeignKey('project.PublishedProject', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='news')
    guid = models.CharField(max_length=64, default=uuid.uuid4)
    created_by = models.ForeignKey('user.User', null=True,
        related_name='news', on_delete=models.SET_NULL)

    def __str__(self):
        return '{} - {}'.format(self.title, self.publish_datetime.date())
