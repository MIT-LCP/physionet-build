import logging

from django.core.management.base import BaseCommand
from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone

import notification.utility as notification
from user.models import CredentialApplication, User

LOGGER = logging.getLogger(__name__)
REJECTION_MESSAGE = 'Your Reference {reference_name} did not respond to the reference check request within '\
                            f'{settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION} days.'

class Command(BaseCommand):

    def handle(self, *args, **options):
        """
        Delete all Credentialing applications whose reference checks have Awaiting Reference Response pending after
        waiting for settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION days.
        """

        today = timezone.now()
        limit = today - timezone.timedelta(days=settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION)

        # user who is responsible for rejecting the application
        responder = User.objects.get(username='admin')

        # creating an instance of HttpRequest to be used in the notification utility
        request = HttpRequest()

        # get all applications that have decision pending
        applications = CredentialApplication.objects.filter(status=0)
        # get applications with Reference Response pending
        response_applications = applications.filter(credential_review__status=30)
        # finally get applications that have been pending for more than the limit
        filtered_applications = response_applications.filter(reference_contact_datetime__lt=limit)

        LOGGER.info(f'Found {len(filtered_applications)} applications to be rejected.')
        for application in filtered_applications:
            application.reject(responder=responder)
            rejection_reason = REJECTION_MESSAGE.format(reference_name=application.reference_name)
            application.responder_comments = rejection_reason
            application.save()
            LOGGER.info(f'Application {application.id} rejected')

            # send notification to applicant
            notification.process_credential_complete(request, application)
            LOGGER.info(f'Notification sent to applicant {application.get_full_name()}')
