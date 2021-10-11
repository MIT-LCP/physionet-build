import datetime as dt

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

from physionet.enums import LogCategory


class BaseQuerySet(QuerySet):
    def update_or_create(self, defaults=None, **kwargs):
        if not kwargs.get('user') or not kwargs.get('project'):
            raise ValueError("You have to provide 'project' and 'user' keyword arguments.")

        created = False
        try:
            instance = self.filter(user=kwargs['user'], project=kwargs['project'])[0]
            if instance.last_access_datetime + dt.timedelta(minutes=settings.LOG_TIMEDELTA) > timezone.now():
                instance.count += 1
                instance.save(update_fields=['count'])
            else:
                instance = self.create(**kwargs)
                created = True
        except IndexError:
            instance = self.create(**kwargs)
            created = True

        return instance, created

class AccessLogQuerySet(BaseQuerySet):
    def create(self, **kwargs):
        kwargs['category'] = LogCategory.ACCESS
        return super().create(**kwargs)


class GCPLogQuerySet(BaseQuerySet):
    def create(self, **kwargs):
        kwargs['category'] = LogCategory.GCP
        return super().create(**kwargs)
