from ckeditor.fields import RichTextField
from django.db import models


class News(models.Model):
    """
    """
    title = models.CharField(max_length=40)
    content = RichTextField()
    publish_datetime = models.DateTimeField(auto_now_add=True)
    url = models.URLField(default='', blank=True)

    def __str__(self):
        return '{} - {}'.format(self.title, self.publish_datetime.date())
