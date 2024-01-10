from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

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

    def s3_uri(self):
        if self.is_private:
            return f's3://{self.bucket_name}/{self.project.version}/'
        else:
            return f's3://{self.bucket_name}/{self.project.slug}/{self.project.version}/'

    def __str__(self):
        return self.s3_uri()
