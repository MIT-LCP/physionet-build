from django.db import models


class DataAccess(models.Model):
    """
    Store all the information for different types of file access.
    platform = local, AWS or GCP
    location = the platform specific identifier referencing the data
    """
    PLATFORM_ACCESS = (
        (0, 'local'),
        (1, 'aws-open-data'),
        (2, 'aws-s3'),
        (3, 'gcp-bucket'),
        (4, 'gcp-bigquery'),
    )

    project = models.ForeignKey('project.PublishedProject',
        related_name='%(class)ss', db_index=True, on_delete=models.CASCADE)
    platform = models.PositiveSmallIntegerField(choices=PLATFORM_ACCESS)
    location = models.CharField(max_length=100, null=True)

    class Meta:
        default_permissions = ()
