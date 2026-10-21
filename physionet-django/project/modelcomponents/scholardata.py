from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone


class ScholarData(models.Model):
    """
    Dataset statistics from the ScholarData API, stored per DOI.

    Fetching happens in a background task so that web requests never
    wait on the external API. `data` holds the last successful response
    (or None if no fetch has succeeded yet). `refresh_datetime` is when
    a refresh was last queued, and is used to avoid queuing duplicates.
    """
    REFRESH_INTERVAL = timedelta(hours=24)

    doi = models.CharField(max_length=255, unique=True)
    data = models.JSONField(null=True, blank=True)
    refresh_datetime = models.DateTimeField()

    class Meta:
        default_permissions = ()

    def __str__(self):
        return self.doi

    @classmethod
    def get_data(cls, doi):
        """
        Return the stored data for a DOI, queuing a refresh if the data
        is missing or stale.

        At most one refresh is queued per DOI per REFRESH_INTERVAL, even
        with concurrent requests: the refresh is claimed by a conditional
        update of refresh_datetime, committed together with the queued
        task. Refreshes run at low priority so they never delay other
        background tasks.
        """
        from project.tasks import refresh_scholar_data

        now = timezone.now()
        cutoff = now - cls.REFRESH_INTERVAL
        with transaction.atomic():
            record, created = cls.objects.get_or_create(
                doi=doi, defaults={'refresh_datetime': now})
            if created:
                claimed = True
            elif record.refresh_datetime < cutoff:
                claimed = cls.objects.filter(
                    pk=record.pk, refresh_datetime__lt=cutoff,
                ).update(refresh_datetime=now)
            else:
                claimed = False
            if claimed:
                refresh_scholar_data(doi, priority=-1)
        return record.data
