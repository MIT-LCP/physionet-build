import logging
from io import StringIO

from django.conf import settings
from django.core.management import call_command

from user.management.commands.utility import get_credential_awaiting_reference
from user.test_views import TestMixin

LOGGER = logging.getLogger(__name__)


class TestRemindPendingCredentialingApplications(TestMixin):

    def test_reminder(self):

        # load list of applications to be reminded
        applications = get_credential_awaiting_reference(
            n=settings.DEFAULT_NUMBER_OF_APPLICATIONS_TO_REMIND,
            days=settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REMINDER,
            ignore_reminded_application=True)

        LOGGER.info(f'Found {len(applications)} applications to be reminded.')

        # call the management command to auto remind applications
        out = StringIO()
        call_command('remind_reference_identity_check',
                     number=settings.DEFAULT_NUMBER_OF_APPLICATIONS_TO_REMIND, stdout=out)

        # check if the users are reminded
        if settings.ENABLE_CREDENTIALING_AUTO_REJECTION:
            for application in applications:
                application.refresh_from_db()
                self.assertIsNotNone(application.reference_reminder_datetime)

        else:
            LOGGER.info('Auto rejection of credentialing applications is disabled. No reminder sent. Exiting.')
