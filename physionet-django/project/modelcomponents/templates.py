from django.db import models

from physionet.enums import Page
from project.models import SafeHTMLField


class Section(models.Model):
    page = models.CharField(max_length=16, choices=Page.choices())
    title = models.CharField(max_length=64)
    content = SafeHTMLField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('order',)
        unique_together = (('page', 'order'),)
