import uuid

from django.conf import settings
from django.db import models

from project.models import SafeHTMLField


class NotificationType(models.IntegerChoices):
    AUTHOR_INVITATION = 1, 'Author invitation'
    INVITATION_RESPONSE = 2, 'Invitation response'
    EDITOR_DECISION = 3, 'Editor decision'
    PROJECT_PUBLISHED = 4, 'Project published'
    PROJECT_SUBMISSION = 5, 'Project submission'
    EDITOR_ASSIGNMENT = 6, 'Editor assignment'
    COPYEDIT = 7, 'Copyedit'
    STORAGE_REQUEST = 8, 'Storage request'
    CREDENTIAL_DECISION = 9, 'Credential decision'
    COHOST_INVITATION = 10, 'Cohost invitation'
    COHOST_RESPONSE = 11, 'Cohost response'
    GENERIC = 12, 'Generic'


class Notification(models.Model):
    """
    Model to record in-app notifications. The recipient is the user who sees the
    notification. The actor is the user whose action triggered it (if any).
    """
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.IntegerField(
        choices=NotificationType.choices,
        default=NotificationType.GENERIC,
    )
    message = models.CharField(max_length=500)
    url = models.CharField(max_length=500, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_datetime = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acted_notifications',
    )

    class Meta:
        ordering = ['-created_datetime']
        indexes = [
            models.Index(
                fields=['recipient', 'is_read', '-created_datetime'],
                name='notif_recipient_unread_idx',
            ),
        ]

    def __str__(self):
        return f'{self.recipient} - {self.message[:50]}'


class News(models.Model):
    """
    Model to record news and announcements.
    """
    title = models.CharField(max_length=150)
    content = SafeHTMLField()
    publish_datetime = models.DateTimeField(auto_now_add=True)
    url = models.URLField(default='', blank=True)
    project = models.ForeignKey(
        'project.PublishedProject',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='news'
    )
    link_all_versions = models.BooleanField(
        default=False,
        help_text='Check this to link the news item to all versions of the selected project'
    )
    guid = models.CharField(max_length=64, default=uuid.uuid4)
    front_page_banner = models.BooleanField(default=False)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        default_permissions = ('change',)

    def __str__(self):
        return '{} - {}'.format(self.title, self.publish_datetime.date())
