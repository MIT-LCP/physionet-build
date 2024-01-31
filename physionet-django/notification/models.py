import uuid

from django.db import models

from project.models import SafeHTMLField


class News(models.Model):
    """
    Model to record news and announcements.
    """
    title = models.CharField(max_length=100)
    content = SafeHTMLField()
    publish_datetime = models.DateTimeField(auto_now_add=True)
    url = models.URLField(default='', blank=True)
    project = models.ForeignKey(
        'project.PublishedProject',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='news'
    )
    link_all_versions = models.BooleanField(
        default=False,
        help_text='Check this to link the news item to all versions of the selected project'
    )
    guid = models.CharField(max_length=64, default=uuid.uuid4)
    front_page_banner = models.BooleanField(default=False)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        default_permissions = ('change',)

    def __str__(self):
        return '{} - {}'.format(self.title, self.publish_datetime.date())
