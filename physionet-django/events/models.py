from django.db import models, transaction
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from django.contrib.auth.models import Permission
from events.enums import EventCategory
from events import validators
from project.modelcomponents.fields import SafeHTMLField
from project.validators import validate_version, validate_slug


class Event(models.Model):
    """
    Captures information on events such as datathons, workshops and classes.
    Used to allow event hosts to assist with credentialing.
    """
    title = models.CharField(max_length=128)
    description = SafeHTMLField(max_length=10000, blank=True, null=True)
    category = models.CharField(choices=EventCategory.choices, max_length=32)
    host = models.ForeignKey("user.User", on_delete=models.CASCADE)
    added_datetime = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    slug = models.SlugField(unique=True)
    allowed_domains = models.CharField(blank=True, null=True, validators=[
                                       validators.validate_domain_list], max_length=100)

    class Meta:
        unique_together = ('title', 'host')
        permissions = [('view_all_events', 'Can view all events in the console'),
                       ('view_event_menu', 'Can view event menu in the navbar')]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = get_random_string(length=12)
        super(Event, self).save(*args, **kwargs)

    def __str__(self):
        return self.title

    def join_waitlist(self, user, comment_to_applicant=None):
        """
       Adds a participant to an event's waitlist.

        Args:
            user (User): The user to add to the event.
            comment_to_applicant (str): The comment to add to the participant about the status.
        """
        with transaction.atomic():
            EventApplication.objects.create(user=user, event=self, comment_to_applicant=comment_to_applicant)
            permission = Permission.objects.get(codename="view_event_menu",
                                                content_type__app_label="events")
            user.user_permissions.add(permission)

    def get_cohosts(self):
        """
        Returns a list of cohosts for the event.
        """
        return self.participants.filter(is_cohost=True)


class EventParticipant(models.Model):
    """
    Captures information about participants in an event.
    """
    user = models.ForeignKey("user.User", on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='participants')
    added_datetime = models.DateTimeField(auto_now_add=True)
    is_cohost = models.BooleanField(default=False, null=True)

    class Meta:
        unique_together = ('user', 'event')

    def __str__(self):
        return self.user.get_full_name()

    def make_cohost(self):
        self.is_cohost = True
        self.save()

    def remove_cohost(self):
        self.is_cohost = False
        self.save()


class EventApplication(models.Model):
    """
    Captures information about applications for events.
    """
    class EventApplicationStatus(models.TextChoices):
        WAITLISTED = 'WL', _('Waitlisted')
        APPROVED = 'AP', _('Approved')
        NOT_APPROVED = 'NA', _('Not Approved')
        WITHDRAWN = 'WD', _('Withdrawn')

        @classmethod
        def choices_approval(cls):
            return ((cls.APPROVED, cls.APPROVED.label),
                    (cls.NOT_APPROVED, cls.NOT_APPROVED.label))

    user = models.ForeignKey("user.User", on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='applications')
    requested_datetime = models.DateTimeField(auto_now_add=True)
    decision_datetime = models.DateTimeField(null=True)

    comment_to_applicant = models.TextField(max_length=500, default='', blank=True)
    status = models.CharField(default=EventApplicationStatus.WAITLISTED, max_length=2,
                              choices=EventApplicationStatus.choices)

    def __str__(self):
        return self.user.get_full_name()

    def get_status(self):
        return self.EventApplicationStatus(self.status).name.replace("_", " ").title()

    def _apply_decision(self, status, comment_to_applicant=None):
        """
        Applies a decision to a participant.

        Args:
            status (EventParticipationStatus): The status to apply to the participant.
            comment_to_applicant (str): The comment to add to the EventApplication about the status update.
        """
        with transaction.atomic():
            self.comment_to_applicant = comment_to_applicant
            self.status = status
            self.decision_datetime = timezone.now()
            self.save()

    def accept(self, comment_to_applicant=None):
        """
        Accepts a participant to an event.

        Args:
            comment_to_applicant (str): The comment to add to the participant about the status.
        """
        self._apply_decision(self.EventApplicationStatus.APPROVED, comment_to_applicant)
        EventParticipant.objects.create(user=self.user, event=self.event)

    def reject(self, comment_to_applicant=None):
        """
        Rejects a participant to an event.

        Args:
            comment_to_applicant (str): The comment to add to the participant about the status.
        """
        self._apply_decision(self.EventApplicationStatus.NOT_APPROVED, comment_to_applicant)

    def withdraw(self, comment_to_applicant=None):
        """
        Withdraws a participant from an event.

        Args:
            comment_to_applicant (str): The comment to add to the participant about the status.
        """
        self._apply_decision(self.EventApplicationStatus.WITHDRAWN, comment_to_applicant)


class EventAgreement(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, validators=[validate_slug])
    version = models.CharField(max_length=15, default='', validators=[validate_version])
    is_active = models.BooleanField(default=True)
    html_content = SafeHTMLField(default='')
    access_template = SafeHTMLField(default='')
    creator = models.ForeignKey("user.User", on_delete=models.CASCADE)

    class Meta:
        default_permissions = ('add',)
        unique_together = (('name', 'version'),)

    def __str__(self):
        return self.name


class EventAgreementSignature(models.Model):
    """
    Log of user signing EventAgreement
    """
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE)
    event_agreement = models.ForeignKey('events.EventAgreement', on_delete=models.CASCADE)
    user = models.ForeignKey('user.User', on_delete=models.CASCADE,
                             related_name='event_agreement_signatures')
    sign_datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()


class EventDataset(models.Model):
    """
    Captures information about datasets for events.
    """

    class EventDatasetAccessType(models.TextChoices):
        GOOGLE_BIG_QUERY = 'GBQ', _('Google BigQuery')
        RESEARCH_ENVIRONMENT = 'RE', _('Research Environment')

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='datasets')
    dataset = models.ForeignKey("project.PublishedProject", on_delete=models.CASCADE)
    access_type = models.CharField(default=EventDatasetAccessType.GOOGLE_BIG_QUERY, max_length=10,
                                   choices=EventDatasetAccessType.choices)
    is_active = models.BooleanField(default=True)
    added_datetime = models.DateTimeField(auto_now_add=True)
    updated_datetime = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.event.title + ' -- ' + self.dataset.title

    def is_accessible(self):
        """
        checks if the dataset is accessible to the user
        Dataset is accessible if:
        1. The dataset is active
        2. The event has not ended
        """
        if not self.is_active:
            return False

        if timezone.now().date() > self.event.end_date:
            return False
        return True

    def has_access(self, user):
        """
        Deprecated: use projects.authorization.access.has_access_to_event_dataset instead
        Checks if the user has access to this EventDataset.
        This does not check if the associated dataset(PublishedProject) is accessible
        """
        if not self.is_accessible():
            return False

        # check if the user is a participant of the event or the host of the event
        # In addition to participants, host should also have access to the dataset of their own event
        # we dont need to worry about cohosts here as they are already participants
        if not self.event.participants.filter(user=user).exists() and not self.event.host == user:
            return False

        # TODO once Event Agreement/DUA is merged, check if the user has accepted the agreement

        return True

    def revoke_dataset_access(self):
        """
        Revokes access to the dataset for the event.
        """
        self.is_active = False
        self.save()
