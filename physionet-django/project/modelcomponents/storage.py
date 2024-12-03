from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.conf import settings
from project.modelcomponents.generic import BaseInvitation
from project.modelcomponents.middleware import get_current_request


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
        """
        Construct the S3 URI for the project.
        """
        from project.cloud.s3 import get_access_point_name_for_user_and_project
        if self.is_private:
            # Retrieve the current request
            request = get_current_request()
            if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
                print("Error: No valid user in the current request.")
                return None

            # Get the current user from the request
            current_user = request.user
            # Fetch access point name
            access_point_name = get_access_point_name_for_user_and_project(current_user, self)
            if access_point_name and "No " not in access_point_name:
                return (
                    f's3://arn:aws:s3:us-east-1:{settings.AWS_ACCOUNT_ID}:accesspoint/'
                    f'{access_point_name}/{self.project.slug}/{self.project.version}/'
                )
            else:
                print(f"Error: {access_point_name}")
                return None

        # For public projects, construct URI using bucket name
        return f's3://{self.bucket_name}/{self.project.slug}/{self.project.version}/'

    def __str__(self):
        return self.s3_uri()


class AWSAccessPoint(models.Model):
    aws = models.ForeignKey(AWS, related_name='access_points', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    users = models.ManyToManyField(
        'user.User',
        through='AWSAccessPointUser',
        related_name='linked_access_points'
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

    class Meta:
        unique_together = [('access_point', 'user')]

    def __str__(self):
        return f"User: {self.user}, Access Point: {self.access_point}"
