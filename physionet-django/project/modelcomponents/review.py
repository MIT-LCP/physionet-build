from django.conf import settings
from django.db import models


class ReviewerInvitation(models.Model):
    """
    An invitation for an external reviewer to review a project submission.
    """
    project = models.ForeignKey(
        'project.ActiveProject',
        on_delete=models.CASCADE,
        related_name='reviewer_invitations',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviewer_invitations',
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_reviewer_invitations',
    )
    invitation_datetime = models.DateTimeField(auto_now_add=True)
    response_datetime = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    review_deadline = models.DateField()

    class Meta:
        default_permissions = ()
        unique_together = (('project', 'reviewer'),)

    def __str__(self):
        return f'Review invitation for {self.reviewer} on {self.project}'


class ExternalReview(models.Model):
    """
    A structured review submitted by an external reviewer.
    """
    RECOMMENDATION_CHOICES = (
        (1, 'Accept'),
        (2, 'Minor Revisions'),
        (3, 'Major Revisions'),
        (4, 'Reject'),
    )

    RATING_CHOICES = (
        (1, '1 - Poor'),
        (2, '2 - Below Average'),
        (3, '3 - Average'),
        (4, '4 - Good'),
        (5, '5 - Excellent'),
    )

    invitation = models.OneToOneField(
        ReviewerInvitation,
        on_delete=models.CASCADE,
        related_name='review',
    )
    recommendation = models.PositiveSmallIntegerField(
        choices=RECOMMENDATION_CHOICES,
    )
    comments_to_editor = models.TextField(
        help_text='Private comments visible only to the editor.',
    )
    comments_to_author = models.TextField(
        help_text='Comments that may be shared with the author.',
    )
    quality_of_writing = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        null=True,
        blank=True,
    )
    significance = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        null=True,
        blank=True,
    )
    technical_validity = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        null=True,
        blank=True,
    )
    submitted_datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f'Review by {self.invitation.reviewer} on {self.invitation.project}'
