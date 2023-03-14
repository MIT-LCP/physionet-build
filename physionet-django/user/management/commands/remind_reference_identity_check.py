import logging

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone


import notification.utility as notification
from user.management.commands.utility import get_credential_awaiting_reference

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("-n", "--number", type=int, help="Number of applications to be reminded")

    def handle(self, *args, **options):
        """
        Remind all Credentialing applications whose reference checks have Awaiting Reference Response pending after
        waiting for settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REMINDER days.
        """

        # only perform auto reminder if the setting.ENABLE_CREDENTIALING_AUTO_REJECTION is True
        if not settings.ENABLE_CREDENTIALING_AUTO_REJECTION:
            LOGGER.info('Auto rejection of credentialing applications is disabled. Exiting.')
            LOGGER.warning('If this was unintentional, please set '
                           'ENABLE_CREDENTIALING_AUTO_REJECTION to True in .env file.')
            return

        total_applications_to_remind = options['number'] or settings.DEFAULT_NUMBER_OF_APPLICATIONS_TO_REMIND
        auto_rejection_days = (settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION
                               - settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REMINDER)
        # creating an instance of HttpRequest to be used in the notification utility
        request = HttpRequest()

        filtered_applications = get_credential_awaiting_reference(
            n=total_applications_to_remind,
            days=settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REMINDER,
            ignore_reminded_application=True)

        LOGGER.info(f'{len(filtered_applications)} credentialing applications selected for reminder.'
                    f' No ref response.')
        for application in filtered_applications:
            with transaction.atomic():
                application.reference_reminder_datetime = timezone.now()
                application.save()
                notification.remind_reference_identity_check(request, application, auto_rejection_days)
                LOGGER.info(f'Reminded ApplicationID: {application.id}. Notification sent to applicant: '
                            f'{application.get_full_name()}')
