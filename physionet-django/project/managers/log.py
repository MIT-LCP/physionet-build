import datetime as dt
from collections import defaultdict

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet, Manager, Min
from django.utils import timezone

from physionet.enums import LogCategory


class AccessLogManager(Manager):
    def get_queryset(self):
        return super().get_queryset().filter(category=LogCategory.ACCESS)


class GCPLogManager(Manager):
    def get_queryset(self):
        return super().get_queryset().filter(category=LogCategory.GCP)


class AccessLogQuerySet(QuerySet):
    def create(self, **kwargs):
        kwargs['category'] = LogCategory.ACCESS
        return super().create(**kwargs)

    def unique_viewers_count(self):
        """Count unique users who have viewed."""
        return self.values('user').distinct().count()

    def first_views_by_month(self):
        """
        Count first-time viewers per month.
        Each user is only counted in the month of their first view.
        """
        first_views = self.values('user').annotate(first_view=Min('creation_datetime'))

        monthly_counts = defaultdict(int)
        for fv in first_views:
            month = fv['first_view'].replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            monthly_counts[month] += 1

        return [{'month': m, 'count': c} for m, c in sorted(monthly_counts.items())]

    def update_or_create(self, defaults=None, **kwargs):
        user = kwargs.get('user')
        project = kwargs.get('project')
        if user is None or project is None:
            raise ValueError("You have to provide 'project' and 'user' keyword arguments.")

        created = False
        try:
            instance = self.filter(
                user=user,
                object_id=project.id,
                content_type=ContentType.objects.get_for_model(project),
            ).order_by("-creation_datetime")[0]
            if instance.last_access_datetime + dt.timedelta(minutes=settings.LOG_TIMEDELTA) > timezone.now():
                instance.count += 1
                instance.save()
            else:
                instance = self.create(**kwargs)
                created = True
        except IndexError:
            instance = self.create(**kwargs)
            created = True

        return instance, created


class GCPLogQuerySet(QuerySet):
    def create(self, **kwargs):
        kwargs['category'] = LogCategory.GCP
        return super().create(**kwargs)

    def update_or_create(self, defaults=None, **kwargs):
        user = kwargs.get('user')
        project = kwargs.get('project')
        data = kwargs.get('data')
        if user is None or project is None or data is None:
            raise ValueError("You have to provide 'project' and 'user' keyword arguments.")

        created = False
        try:
            instance = self.filter(
                user=user,
                object_id=project.id,
                data=data,
                content_type=ContentType.objects.get_for_model(project),
            ).order_by("-creation_datetime")[0]
            if instance.last_access_datetime + dt.timedelta(minutes=settings.LOG_TIMEDELTA) > timezone.now():
                instance.count += 1
                instance.save()
            else:
                instance = self.create(**kwargs)
                created = True
        except IndexError:
            instance = self.create(**kwargs)
            created = True

        return instance, created
