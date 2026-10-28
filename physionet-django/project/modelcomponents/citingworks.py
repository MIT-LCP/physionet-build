from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone


class CitingWork(models.Model):
    """
    A published work that cites a project, as reported by OpenAlex.

    Works are stored per CoreProject, so every version of a project
    shares one list. `cites_dataset` is set if the work cites one of the
    project's DOIs, and `cites_publication` if it cites the project's
    primary publication (a work may cite both).
    """
    core_project = models.ForeignKey('project.CoreProject', related_name='citing_works',
                                     on_delete=models.CASCADE)
    openalex_id = models.CharField(max_length=32)
    doi = models.CharField(max_length=255, blank=True, default='')
    title = models.CharField(max_length=1000)
    authors = models.CharField(max_length=1000, blank=True, default='')
    venue = models.CharField(max_length=500, blank=True, default='')
    publication_date = models.DateField(null=True, blank=True)
    cites_dataset = models.BooleanField(default=False)
    cites_publication = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['core_project', 'openalex_id'],
                                    name='unique_citing_work_per_core_project'),
        ]

    def __str__(self):
        return self.title

    @property
    def url(self):
        if self.doi:
            return f'https://doi.org/{self.doi}'
        return f'https://openalex.org/{self.openalex_id}'

    @classmethod
    def newest_first(cls, core_project):
        """
        Return the works citing a project, newest first.
        """
        return cls.objects.filter(core_project=core_project).order_by(
            models.F('publication_date').desc(nulls_last=True), 'title')


class CitingWorksRefresh(models.Model):
    """
    When the list of works citing a project was last refreshed.

    `refresh_datetime` is when a refresh was last queued, and is used to
    avoid queuing duplicates. `fetch_datetime` is when a refresh last
    succeeded (None if none has succeeded yet).
    """
    REFRESH_INTERVAL = timedelta(days=7)

    core_project = models.OneToOneField('project.CoreProject', related_name='citing_works_refresh',
                                        on_delete=models.CASCADE)
    refresh_datetime = models.DateTimeField()
    fetch_datetime = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ()

    @classmethod
    def request_refresh(cls, core_project):
        """
        Queue a refresh of the works citing a project if the stored list
        is missing or stale.

        Works the same way as ScholarData.get_data: at most one refresh
        is queued per project per REFRESH_INTERVAL, even with concurrent
        requests, and refreshes run at low priority.
        """
        from project.tasks import refresh_citing_works

        now = timezone.now()
        cutoff = now - cls.REFRESH_INTERVAL
        with transaction.atomic():
            record, created = cls.objects.get_or_create(
                core_project=core_project, defaults={'refresh_datetime': now})
            if created:
                claimed = True
            elif record.refresh_datetime < cutoff:
                claimed = cls.objects.filter(
                    pk=record.pk, refresh_datetime__lt=cutoff,
                ).update(refresh_datetime=now)
            else:
                claimed = False
            if claimed:
                refresh_citing_works(str(core_project.id), priority=-1)
