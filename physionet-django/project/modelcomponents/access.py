from datetime import timedelta
from enum import IntEnum

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from project.modelcomponents.fields import SafeHTMLField
from project.validators import validate_version

from project.managers.access import DataAccessRequestQuerySet, DataAccessRequestManager


class AccessPolicy(IntEnum):
    OPEN = 0
    RESTRICTED = 1
    CREDENTIALED = 2
    CONTRIBUTOR_REVIEW = 3

    do_not_call_in_templates = True

    @classmethod
    def choices(cls, gte_value=0):
        return tuple(
            (option.value, option.name.replace("_", " ").title())
            for option in cls if option.value >= gte_value
        )


class DUASignature(models.Model):
    """
    Log of user signing DUA
    """
    project = models.ForeignKey('project.PublishedProject',
        on_delete=models.CASCADE)
    user = models.ForeignKey('user.User', on_delete=models.CASCADE,
                             related_name='dua_signatures')
    sign_datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()


class DataAccessRequest(models.Model):
    PENDING_VALUE = 0
    REJECT_REQUEST_VALUE = 1
    WITHDRAWN_VALUE = 2
    ACCEPT_REQUEST_VALUE = 3
    REVOKED_VALUE = 4

    REJECT_ACCEPT = (
        (REJECT_REQUEST_VALUE, 'Reject'),
        (ACCEPT_REQUEST_VALUE, 'Accept'),
    )

    status_texts = {
        PENDING_VALUE: "pending",
        REJECT_REQUEST_VALUE: "rejected",
        WITHDRAWN_VALUE: "withdrawn",
        ACCEPT_REQUEST_VALUE: "accepted",
        REVOKED_VALUE: "revoked",
    }

    DATA_ACCESS_REQUESTS_DAY_LIMIT = 365

    request_datetime = models.DateTimeField(auto_now_add=True)

    requester = models.ForeignKey('user.User', on_delete=models.CASCADE)

    project = models.ForeignKey('project.PublishedProject',
                                related_name='data_access_requests',
                                on_delete=models.CASCADE)

    data_use_title = models.CharField(max_length=200, default='')
    data_use_purpose = SafeHTMLField(blank=False, max_length=10000)

    status = models.PositiveSmallIntegerField(default=0, choices=REJECT_ACCEPT)

    decision_datetime = models.DateTimeField(null=True)

    duration = models.DurationField(null=True, blank=True)

    responder = models.ForeignKey('user.User', null=True,
                                  related_name='data_access_request_user',
                                  on_delete=models.SET_NULL)

    responder_comments = SafeHTMLField(blank=True, max_length=10000)

    objects = DataAccessRequestManager.from_queryset(DataAccessRequestQuerySet)()

    class Meta:
        default_permissions = ()

    def is_accepted(self):
        return self.status == self.ACCEPT_REQUEST_VALUE and (
            self.duration is None or self.decision_datetime + self.duration > timezone.now()
        )

    def is_rejected(self):
        return self.status == self.REJECT_REQUEST_VALUE

    def is_withdrawn(self):
        return self.status == self.WITHDRAWN_VALUE

    def is_pending(self):
        return self.status == self.PENDING_VALUE

    def is_revoked(self):
        return self.status == self.REVOKED_VALUE

    def status_text(self):
        return self.status_texts.get(self.status, 'unknown')


class DataAccessRequestReviewer(models.Model):
    """
    A user who is invited to review data access requests of self managed
    credentialing projects.
    """
    project = models.ForeignKey('project.PublishedProject',
                                related_name='data_access_request_reviewers',
                                on_delete=models.CASCADE)

    reviewer = models.ForeignKey('user.User', on_delete=models.CASCADE,
                                 related_name='data_access_request_reviewers')

    added_date = models.DateTimeField(auto_now_add=True)

    is_revoked = models.BooleanField(default=False)

    revocation_date = models.DateTimeField(null=True)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=['project', 'reviewer'], name='unique project reviewer')
        ]

    def revoke(self):
        self.revocation_date = timezone.now()
        self.is_revoked = True
        self.save()


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


class DataSource(models.Model):
    """
    Controls all access to project data.
    """
    class DataLocation(models.TextChoices):
        DIRECT = 'Direct'
        GOOGLE_BIGQUERY = 'Google BigQuery'
        GOOGLE_CLOUD_STORAGE = 'Google Cloud Storage'
        AWS_OPEN_DATA = 'AWS Open Data'
        AWS_S3 = 'AWS S3'

    class AccessMechanism(models.TextChoices):
        GOOGLE_GROUP_EMAIL = 'Google Group Email'
        S3 = 'S3'
        RESEARCH_ENVIRONMENT = 'Research Environment'

    project = models.ForeignKey('project.PublishedProject',
                                related_name='data_sources', db_index=True, on_delete=models.CASCADE)
    files_available = models.BooleanField(default=False)
    data_location = models.CharField(max_length=20, choices=DataLocation.choices)
    access_mechanism = models.CharField(max_length=20, choices=AccessMechanism.choices, null=True, blank=True)
    email = models.EmailField(max_length=320, null=True, blank=True)
    uri = models.CharField(max_length=320, null=True, blank=True)

    class Meta:
        default_permissions = ()
        unique_together = ('project', 'data_location')

    def clean(self):
        super().clean()

        # all the fields in the list are expected to be present for the given data_location
        required_fields_data_location = {
            self.DataLocation.GOOGLE_BIGQUERY: ["email"],
            self.DataLocation.GOOGLE_CLOUD_STORAGE: ["uri"],
            self.DataLocation.AWS_OPEN_DATA: ["uri"],
            self.DataLocation.AWS_S3: ["uri"],
            # self.DataLocation.DIRECT: []
        }
        # one of the access_mechanism in the list is expected to be present for the given data_location
        required_access_mechanism_data_location = {
            self.DataLocation.GOOGLE_BIGQUERY: [self.AccessMechanism.GOOGLE_GROUP_EMAIL],
            self.DataLocation.GOOGLE_CLOUD_STORAGE: [self.AccessMechanism.GOOGLE_GROUP_EMAIL,
                                                     self.AccessMechanism.RESEARCH_ENVIRONMENT],
            self.DataLocation.AWS_OPEN_DATA: [self.AccessMechanism.S3],
            self.DataLocation.AWS_S3: [self.AccessMechanism.S3],
            # self.DataLocation.DIRECT: []
        }
        # None of the access_mechanism in the list are expected be present for the given data_location
        forbidden_access_mechanism_data_location = {
            self.DataLocation.DIRECT: [self.AccessMechanism.GOOGLE_GROUP_EMAIL, self.AccessMechanism.S3,
                                       self.AccessMechanism.RESEARCH_ENVIRONMENT]
        }
        # None the fields in the list are expected to not be present for the given data_location
        forbidden_fields_data_location = {
            self.DataLocation.DIRECT: ["uri", "email"]
        }

        if self.data_location in required_access_mechanism_data_location:
            if self.access_mechanism not in required_access_mechanism_data_location.get(self.data_location, []):
                raise ValidationError(
                    f'{self.data_location} data sources must use one of the following access mechanisms: '
                    f'{", ".join(required_access_mechanism_data_location.get(self.data_location, []))}.')

        if self.data_location in forbidden_access_mechanism_data_location:
            if self.access_mechanism in forbidden_access_mechanism_data_location.get(self.data_location, []):
                raise ValidationError(
                    f'{self.data_location} data sources must not use the following access mechanisms: '
                    f'{", ".join(forbidden_access_mechanism_data_location.get(self.data_location, []))}.')

        if self.data_location in required_fields_data_location:
            for required_field in required_fields_data_location.get(self.data_location, []):
                if not getattr(self, required_field):
                    raise ValidationError(f'{self.data_location} data sources must have a {required_field}.')

        if self.data_location in forbidden_fields_data_location:
            for forbidden_field in forbidden_fields_data_location.get(self.data_location, []):
                if getattr(self, forbidden_field):
                    raise ValidationError(f'{self.data_location} sources must not have a {forbidden_field}.')


class AnonymousAccess(models.Model):
    """
    Makes it possible to grant anonymous access (without user auth)
    to a project and its files by authenticating with a passphrase.
    """
    # Project GenericFK
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    # Stores hashed passphrase
    passphrase = models.CharField(max_length=128)

    # Random url
    url = models.CharField(max_length=64)

    # Record tracking
    creation_datetime = models.DateTimeField(auto_now_add=True)
    expiration_datetime = models.DateTimeField(null=True)
    creator = models.ForeignKey('user.User', related_name='anonymous_access_creator',
        on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        default_permissions = ()
        unique_together = (("content_type", "object_id"),)

    def generate_access(self):
        url = self.generate_url()
        passphrase = self.set_passphrase()

        return url, passphrase

    def generate_url(self):
        url = get_random_string(64)

        # Has to be unique
        while AnonymousAccess.objects.filter(url=url).first():
            url = get_random_string(64)

        # Persist new url
        self.url = url
        self.save()

        return url

    def set_passphrase(self):
        # Generate and encode random password
        raw = get_random_string(20)

        # Store encoded passphrase
        self.passphrase = make_password(raw, salt='project.AnonymousAccess')
        self.save()

        return raw

    def check_passphrase(self, raw_passphrase):
        """
        Return a boolean of whether the raw_password was correct. Handles
        hashing formats behind the scenes.
        """
        expire_datetime = self.creation_datetime + timedelta(days=180)
        isnot_expired = timezone.now() < expire_datetime

        return isnot_expired and check_password(raw_passphrase, self.passphrase)


class License(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    version = models.CharField(max_length=15, default='', validators=[validate_version])
    is_active = models.BooleanField(default=True)
    text_content = models.TextField(default='')
    html_content = SafeHTMLField(default='')
    home_page = models.URLField()
    # A project must choose a license with a matching access policy and
    # compatible resource type
    access_policy = models.PositiveSmallIntegerField(choices=AccessPolicy.choices(), default=AccessPolicy.OPEN)
    # A license can be used for one or more resource types.
    # This is a comma delimited char field containing allowed types.
    # ie. '0' or '0,2' or '1,3,4'
    project_types = models.ManyToManyField('project.ProjectType', related_name='licenses')
    # A protected license has associated DUA content

    class Meta:
        default_permissions = ('add',)
        unique_together = (('name', 'version'),)

    def __str__(self):
        return self.name


class DUA(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    version = models.CharField(max_length=15, default='', validators=[validate_version])
    is_active = models.BooleanField(default=True)
    html_content = SafeHTMLField(default='')
    access_template = SafeHTMLField(default='')
    access_policy = models.PositiveSmallIntegerField(choices=AccessPolicy.choices(), default=AccessPolicy.OPEN)
    project_types = models.ManyToManyField('project.ProjectType', related_name='duas')

    class Meta:
        default_permissions = ('add',)
        unique_together = (('name', 'version'),)

    def __str__(self):
        return self.name
