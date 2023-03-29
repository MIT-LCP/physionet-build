from django.db import models
from django.utils import timezone

from authorization.managers.access import DataAccessRequestQuerySet, DataAccessRequestManager
from project.modelcomponents.fields import SafeHTMLField


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

    DATA_ACCESS_REQUESTS_DAY_LIMIT = 14

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
