from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string

from project.modelcomponents.generic import BaseInvitation

# Number of days that an anonymous access link remains valid
ANONYMOUS_ACCESS_DAYS = 180


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

    hide_authors = models.BooleanField(
        default=False,
        help_text="When True, author information is hidden for anonymous peer review"
    )

    # Record tracking
    creation_datetime = models.DateTimeField(auto_now_add=True)
    expiration_datetime = models.DateTimeField(null=True)
    creator = models.ForeignKey('user.User',
                                related_name='anonymous_access_creator',
                                on_delete=models.SET_NULL,
                                null=True, blank=True)

    class Meta:
        default_permissions = ()
        unique_together = (("content_type", "object_id"),)

    def generate_access(self):
        # Restart the validity period when a new link is generated
        self.creation_datetime = timezone.now()
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
        isnot_expired = timezone.now() < self.expiry_datetime

        return isnot_expired and check_password(raw_passphrase, self.passphrase)

    @property
    def expiry_datetime(self):
        """
        The time after which the passphrase is no longer accepted.
        """
        return self.creation_datetime + timedelta(days=ANONYMOUS_ACCESS_DAYS)

    @property
    def is_expired(self):
        return timezone.now() >= self.expiry_datetime


class ReviewerAccessRequest(BaseInvitation):
    """
    A request from an author for a private link that lets journal
    reviewers see a project while it is under submission.

    The request is granted or declined by an editor. Granting it
    creates (or replaces) the project's AnonymousAccess link and
    sends the link and passphrase to the requester.
    """
    requester = models.ForeignKey('user.User', related_name='reviewer_access_requests',
                                  on_delete=models.CASCADE)
    journal = models.CharField(max_length=300,
                               help_text='The journal or venue reviewing the related manuscript')
    hide_authors = models.BooleanField(
        default=False,
        help_text='Whether the author asked for a link that hides author information'
    )
    message = models.TextField(max_length=2000, blank=True, default='')
    responder = models.ForeignKey('user.User', null=True, blank=True, related_name='+',
                                  on_delete=models.SET_NULL)
    response_message = models.TextField(max_length=2000, blank=True, default='')

    class Meta:
        default_permissions = ()

    def __str__(self):
        return 'Reviewer access request for project: {0}'.format(self.project)
