from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.conf import settings
from project.modelcomponents.generic import BaseInvitation

class StorageRequest(BaseInvitation):
    """
    A request for storage capacity for a project
    """
    # Requested storage size in GB. Max = 10Tb
    request_allowance = models.SmallIntegerField(
        validators=[MaxValueValidator(10240), MinValueValidator(1)])
    responder = models.ForeignKey('user.User', null=True,
        on_delete=models.SET_NULL)
    response_message = models.CharField(max_length=10000, default='', blank=True)

    class Meta:
        default_permissions = ('change',)

    def __str__(self):
        return '{0}GB for project: {1}'.format(self.request_allowance,
                                               self.project.__str__())


class GCP(models.Model):
    """
    Store all of the Google Cloud information with a relation to a project.
    """
    project = models.OneToOneField('project.PublishedProject', related_name='gcp',
        on_delete=models.CASCADE)
    bucket_name = models.CharField(max_length=150, null=True)
    access_group = models.CharField(max_length=170, null=True)
    is_private = models.BooleanField(default=False)
    sent_zip = models.BooleanField(default=False)
    sent_files = models.BooleanField(default=False)
    managed_by = models.ForeignKey('user.User', related_name='gcp_manager',
        on_delete=models.CASCADE)
    creation_datetime = models.DateTimeField(auto_now_add=True)
    finished_datetime = models.DateTimeField(null=True)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return self.bucket_name


class AWS(models.Model):
    """
    Store all of the AWS information with a relation to a project.
    """
    project = models.OneToOneField(
        "project.PublishedProject", related_name="aws", on_delete=models.CASCADE
    )
    bucket_name = models.CharField(max_length=150, null=True)
    is_private = models.BooleanField(default=False)
    sent_zip = models.BooleanField(default=False)
    sent_files = models.BooleanField(default=False)
    creation_datetime = models.DateTimeField(auto_now_add=True)
    finished_datetime = models.DateTimeField(null=True)

    class Meta:
        default_permissions = ()

    def public_s3_uri(self):
        """
        Construct the S3 URI for public projects.
        """
        return f's3://{self.bucket_name}/{self.project.slug}/{self.project.version}/'

    def __str__(self):
        return f"AWS instance for project: {self.project.slug}"


class AWSAccessPoint(models.Model):
    aws = models.ForeignKey(AWS, related_name='access_points', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    users = models.ManyToManyField(
        'user.User',
        through='AWSAccessPointUser',
        related_name='linked_access_points'
    )

    def private_s3_uri(self):
        """
        Construct the S3 URI for private projects using an access point.
        """
        return (
            f's3://arn:aws:s3:us-east-1:{settings.AWS_ACCOUNT_ID}:accesspoint/'
            f'{self.name}/{self.aws.project.slug}/{self.aws.project.version}/'
        )


class AWSAccessPointUser(models.Model):
    access_point = models.ForeignKey(
        AWSAccessPoint,
        related_name='linked_users',
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        'user.User',
        related_name='aws_access_point_users',
        on_delete=models.CASCADE
    )
    aws = models.ForeignKey(
        AWS,
        related_name='access_point_users',
        on_delete=models.CASCADE
    )

    class Meta:
        unique_together = [('user', 'aws')]

    def __str__(self):
        return f"User: {self.user}, Access Point: {self.access_point}"
