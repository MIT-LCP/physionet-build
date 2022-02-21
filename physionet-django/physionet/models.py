from django.db import models

from physionet.enums import Page
from project.models import SafeHTMLField


class Section(models.Model):
    page = models.CharField(max_length=16, choices=Page.choices())
    title = models.CharField(max_length=64)
    content = SafeHTMLField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        default_permissions = ('change',)
        ordering = ('order',)
        unique_together = (('page', 'order'),)

    def __str__(self):
        return self.title

    def move_up(self):
        order = self.order
        if order == 1:
            return

        count = Section.objects.count()
        self.order = count + 1
        self.save()

        Section.objects.filter(page=self.page, order=order - 1).update(order=order)

        self.order = order - 1
        self.save()

    def move_down(self):
        count = Section.objects.count()
        order = self.order
        if order == count:
            return

        self.order = count + 1
        self.save()

        Section.objects.filter(page=self.page, order=order + 1).update(order=order)

        self.order = order + 1
        self.save()
