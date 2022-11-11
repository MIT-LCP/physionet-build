from django.db import models

from project.models import SafeHTMLField


class StaticPage(models.Model):
    """
    Allows pages on the site to be created via the admin tool. Controls whether a given page appears in the navigation
    bar.
    """
    title = models.CharField(max_length=64)
    url = models.CharField(max_length=64, unique=True)
    nav_bar = models.BooleanField(default=False)
    front_page = models.BooleanField(default=False)
    nav_order = models.PositiveSmallIntegerField(unique=True, null=True, blank=True)

    class Meta:
        default_permissions = ('change',)

    def __str__(self):
        return self.title


class Section(models.Model):
    """
    Holds sections of content for StaticPage.
    """
    static_page = models.ForeignKey(StaticPage, on_delete=models.CASCADE)
    title = models.CharField(max_length=64)
    content = SafeHTMLField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        default_permissions = ()
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
