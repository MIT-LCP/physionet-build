import logging

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from events.models import Event, EventApplication
import notification.utility as notification

LOGGER = logging.getLogger(__name__)

AUTO_REJECTION_REASON = 'Event has ended.'


class Command(BaseCommand):
    def handle(self, *args, **options):
        """
        Auto reject pending registration applications for events that have ended
        """
        # creating an instance of HttpRequest to be used in the notification utility
        request = HttpRequest()

        past_events = Event.objects.filter(
            end_date__lt=timezone.now(),
            applications__status=EventApplication.EventApplicationStatus.WAITLISTED)

        LOGGER.info(f'{past_events.count()} events selected for auto rejection of waitlisted applications.')

        for event in past_events:
            applications = event.applications.filter(status=EventApplication.EventApplicationStatus.WAITLISTED)
            for application in applications:
                with transaction.atomic():
                    application.reject(comment_to_applicant=AUTO_REJECTION_REASON)
                    notification.notify_participant_event_decision(
                        request=request,
                        user=application.user,
                        event=application.event,
                        decision=EventApplication.EventApplicationStatus.NOT_APPROVED.label,
                        comment_to_applicant=AUTO_REJECTION_REASON
                    )
                    LOGGER.info(f'Application {application.id} for event {event.id} rejected.')
