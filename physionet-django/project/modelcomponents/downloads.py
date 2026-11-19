from django.db import models


class S3AccessLogImport(models.Model):
    """A UTC day of S3 server access logs imported for one data bucket."""
    date = models.DateField()
    bucket = models.CharField(max_length=63)
    requests = models.PositiveIntegerField(default=0)
    import_datetime = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['date', 'bucket'], name='unique_s3_access_log_import'),
        ]


class S3DownloadClientDay(models.Model):
    """
    One client's S3 downloads of a project version on one UTC day.

    Clients are PhysioNet users, or keyed hashes of an unmatched AWS
    principal or of an anonymous IP address and user agent.  The hash
    key changes every month, and these rows are deleted when the month
    is summarized into S3DownloadMonth.
    """
    date = models.DateField()
    bucket = models.CharField(max_length=63)
    project = models.ForeignKey('project.PublishedProject', related_name='+', on_delete=models.CASCADE)
    client = models.CharField(max_length=80)
    user = models.ForeignKey('user.User', null=True, related_name='+', on_delete=models.SET_NULL)
    bytes_sent = models.BigIntegerField(default=0)
    zip_bytes = models.BigIntegerField(default=0)
    requests = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['date', 'bucket', 'project', 'client'],
                                    name='unique_s3_download_client_day'),
        ]


class S3DownloadMonth(models.Model):
    """Monthly S3 download counts for a project version in one bucket, kept after its client rows are deleted."""
    month = models.DateField()
    bucket = models.CharField(max_length=63)
    project = models.ForeignKey('project.PublishedProject', related_name='+', on_delete=models.CASCADE)
    downloads = models.PositiveIntegerField(default=0)
    user_downloads = models.PositiveIntegerField(default=0)
    clients = models.PositiveIntegerField(default=0)
    bytes_sent = models.BigIntegerField(default=0)
    requests = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['month', 'bucket', 'project'], name='unique_s3_download_month'),
        ]
