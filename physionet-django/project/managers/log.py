import datetime as dt

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet, Manager
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
