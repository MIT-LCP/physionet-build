from django.db import models
from django.db import transaction
from project.models import SafeHTMLField


class StaticPage(models.Model):
    """
    Allows pages on the site to be created via the admin tool. Controls whether a given page appears in the navigation
    bar.
    """
    title = models.CharField(max_length=64)
    url = models.CharField(max_length=64, unique=True)
    nav_bar = models.BooleanField(default=False)
    nav_order = models.PositiveSmallIntegerField(unique=True, null=True, blank=True)

    class Meta:
        default_permissions = ('change',)

    def __str__(self):
        return self.title

    def move_up(self):
        nav_order = self.nav_order
        if nav_order == 1:
            return

        count = StaticPage.objects.count()
        # hack to avoid unique constraint(10000 has no significance, it's just a large number)
        self.nav_order = count + 10000
        self.save()

        StaticPage.objects.filter(nav_order=nav_order - 1).update(nav_order=nav_order)

        self.nav_order = nav_order - 1
        self.save()

    def move_down(self):
        count = StaticPage.objects.count()
        nav_order = self.nav_order
        if nav_order == count:
            return
        # hack to avoid unique constraint(10000 has no significance, it's just a large number)
        self.nav_order = count + 10000
        self.save()

        StaticPage.objects.filter(nav_order=nav_order + 1).update(nav_order=nav_order)

        self.nav_order = nav_order + 1
        self.save()

    def delete(self, *args, **kwargs):
        nav_order = self.nav_order

        with transaction.atomic():
            super().delete(*args, **kwargs)
            pages = StaticPage.objects.filter(nav_order__gt=nav_order).order_by('nav_order')
            for page in pages:
                page.nav_order = page.nav_order - 1
                page.save()


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


class FrontPageButton(models.Model):
    """
    Holds front page button detail.
    """
    label = models.CharField(max_length=20, unique=True)
    url = models.CharField(max_length=200, blank=False)
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        default_permissions = ('change',)
        ordering = ('order',)

    def __str__(self):
        return self.label

    def move_up(self):
        order = self.order
        if order == 1:
            return

        count = FrontPageButton.objects.count()
        self.order = count + 1
        self.save()

        FrontPageButton.objects.filter(order=order - 1).update(order=order)

        self.order = order - 1
        self.save()

    def move_down(self):
        count = FrontPageButton.objects.count()
        order = self.order
        if order == count:
            return

        self.order = count + 1
        self.save()

        FrontPageButton.objects.filter(order=order + 1).update(order=order)

        self.order = order + 1
        self.save()
