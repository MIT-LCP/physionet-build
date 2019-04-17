from django.db import models

from project.models import SafeHTMLField


class News(models.Model):
    """
    """
    title = models.CharField(max_length=40)
    content = SafeHTMLField()
    publish_datetime = models.DateTimeField(auto_now_add=True)
    url = models.URLField(default='', blank=True)
    project = models.ForeignKey('project.PublishedProject', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='news')

    def __str__(self):
        return '{} - {}'.format(self.title, self.publish_datetime.date())
