import logging

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest

import notification.utility as notification
from user.models import CredentialApplication, User
from user.management.commands.utility import get_credential_awaiting_reference

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-n", "--number", type=int, help="Number of applications to be rejected")

    def handle(self, *args, **options):
        """
        Delete all Credentialing applications whose reference checks have Awaiting Reference Response pending after
        waiting for settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION days.
        """

        # only perform auto rejection if the setting.ENABLE_CREDENTIALING_AUTO_REJECTION is True
        if not settings.ENABLE_CREDENTIALING_AUTO_REJECTION:
            LOGGER.info('Auto rejection of credentialing applications is disabled. Exiting.')
            LOGGER.warning('If this was unintentional, please set '
                           'MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION to True in .env file.')
            return

        total_applications_to_reject = options['number'] or settings.DEFAULT_NUMBER_OF_APPLICATIONS_TO_REJECT

        # creating an instance of HttpRequest to be used in the notification utility
        request = HttpRequest()

        filtered_applications = get_credential_awaiting_reference(
            n=total_applications_to_reject,
            days=settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION)

        LOGGER.info(f'{len(filtered_applications)} credentialing applications selected for rejection.'
                    f' No ref response.')
        for application in filtered_applications:
            with transaction.atomic():
                application.auto_reject(reason=CredentialApplication.AutoRejectionReason.NO_RESPONSE_FROM_REFERENCE)

                notification.process_credential_complete(request, application)
                LOGGER.info(f'Rejected ApplicationID: {application.id}. Notification sent to applicant: '
                            f'{application.get_full_name()}')
