import logging
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from events.models import Event, EventApplication
from events.tests_views import TestMixin

LOGGER = logging.getLogger(__name__)


class TestRejectPendingCredentialingApplications(TestMixin):

    def test_rejection(self):

        # get dict of applications to be rejected per event
        event_application_dict = {}
        past_events = Event.objects.filter(
            end_date__lt=timezone.now(),
            applications__status=EventApplication.EventApplicationStatus.WAITLISTED)
        for event in past_events:
            event_application_dict[event] = event.applications.filter(
                status=EventApplication.EventApplicationStatus.WAITLISTED
            )[:settings.DEFAULT_NUMBER_OF_APPLICATIONS_TO_REJECT_PER_EVENT]

        LOGGER.info(f'Found {len(past_events)} events with waitlisted applications to be rejected.')

        # call the management command to auto reject applications
        out = StringIO()
        call_command('reject_past_event_applications',
                     number=settings.DEFAULT_NUMBER_OF_APPLICATIONS_TO_REJECT_PER_EVENT, stdout=out)

        if not settings.ENABLE_EVENT_REGISTRATION_AUTO_REJECTION:
            # check if the applications status is unchanged
            LOGGER.info('Auto rejection of event applications is disabled.')
            LOGGER.info('Checking if the applications status is unchanged.')
            for event, applications in event_application_dict.items():
                for application in applications:
                    application.refresh_from_db()
                    self.assertEqual(application.status, EventApplication.EventApplicationStatus.WAITLISTED)
            return

        # check if the applications are rejected
        for event, applications in event_application_dict.items():
            for application in applications:
                application.refresh_from_db()
                self.assertEqual(application.status, EventApplication.EventApplicationStatus.NOT_APPROVED)
                LOGGER.info(f'Application {application.id} for event {event.id} auto rejection confirmed.')
