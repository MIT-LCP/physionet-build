from django.db import models
from django.utils import timezone


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
