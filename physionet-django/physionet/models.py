from django.db import models

from project.models import SafeHTMLField


class StaticPage(models.Model):
    """
    A static page object which holds the url path and whether to link to the page in the nav bar and in what order
    """
    title = models.CharField(max_length=64)
    url = models.CharField(max_length=64, unique=True)
    nav_bar = models.BooleanField(default=False)
    nav_order = models.IntegerField(unique=True, null=True)

    def __str__(self):
        return self.title


class Section(models.Model):
    """
    An object which holds sections of content for static page objects
    """
    static_page = models.ForeignKey(StaticPage, on_delete=models.CASCADE)
    title = models.CharField(max_length=64)
    content = SafeHTMLField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('order',)
        unique_together = (('static_page', 'order'),)

    def __str__(self):
        return self.title

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
