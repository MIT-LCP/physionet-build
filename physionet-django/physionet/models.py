from django.db import models

from project.models import SafeHTMLField


class StaticPage(models.Model):
    title = models.CharField(max_length=64)
    url = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.title


class Section(models.Model):
    static_page = models.ForeignKey(StaticPage, on_delete=models.CASCADE)
    title = models.CharField(max_length=64)
    content = SafeHTMLField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('order',)
        unique_together = (('static_page', 'order'),)

    def __str__(self):
        return self.static_page.title

    def move_up(self):
        order = self.order
        if order == 1:
            return

        count = Section.objects.count()
        self.order = count + 1
        self.save()

        Section.objects.filter(static_page=self.static_page, order=order - 1).update(order=order)

        self.order = order - 1
        self.save()

    def move_down(self):
        count = Section.objects.count()
        order = self.order
        if order == count:
            return

        self.order = count + 1
        self.save()

        Section.objects.filter(static_page=self.static_page, order=order + 1).update(order=order)

        self.order = order + 1
        self.save()
