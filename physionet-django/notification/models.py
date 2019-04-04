from django.db import models

from project.models import SafeHTMLField


class News(models.Model):
    """
    """
    title = models.CharField(max_length=40)
    content = SafeHTMLField()
    publish_datetime = models.DateTimeField(auto_now_add=True)
    url = models.URLField(default='', blank=True)

    def __str__(self):
        return '{} - {}'.format(self.title, self.publish_datetime.date())
