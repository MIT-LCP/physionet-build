from django.db import models, transaction
from django.utils.crypto import get_random_string
from django.utils import timezone

from django.contrib.auth.models import Permission
from events.enums import EventCategory
from events import validators


# Create your models here.
class Event(models.Model):
    """
    Captures information on events such as datathons, workshops and classes.
    Used to allow event hosts to assist with credentialing.
    """
    title = models.CharField(max_length=64)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(choices=EventCategory.choices, max_length=32)
    host = models.ForeignKey("user.User", on_delete=models.CASCADE)
    added_datetime = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    slug = models.SlugField(unique=True, default=get_random_string)
    allowed_domains = models.CharField(blank=True, null=True, validators=[
                                       validators.validate_domain_list], max_length=100)

    class Meta:
        unique_together = ('title', 'host')
        permissions = [('view_all_events', 'Can view all events in the console'),
                       ('view_event_menu', 'Can view event menu in the navbar')]

    def __str__(self):
        return self.title

    def enroll_user(self, user):
        """
        Adds a participant to an event.
        """
        with transaction.atomic():
            EventParticipant.objects.create(user=user, event=self)
            permission = Permission.objects.get(codename="view_event_menu",
                                                content_type__app_label="events")
            user.user_permissions.add(permission)


class EventParticipant(models.Model):
    """
    Captures information about participants in an event.
    """
    user = models.ForeignKey("user.User", on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='participants')
    added_datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'event')

    def __str__(self):
        return self.user.get_full_name()
