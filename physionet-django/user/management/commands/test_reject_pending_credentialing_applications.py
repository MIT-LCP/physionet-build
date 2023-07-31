import logging
from io import StringIO

from django.conf import settings
from django.core.management import call_command

from user.management.commands.utility import get_credential_awaiting_reference
from user.models import CredentialApplication
from user.test_views import TestMixin

LOGGER = logging.getLogger(__name__)


class TestRejectPendingCredentialingApplications(TestMixin):

    def test_rejection(self):

        # load list of applications to be rejected
        applications = get_credential_awaiting_reference(
            n=settings.DEFAULT_NUMBER_OF_APPLICATIONS_TO_REJECT,
            days=settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION)

        LOGGER.info(f'Found {len(applications)} applications to be rejected.')

        # call the management command to auto reject applications
        out = StringIO()
        call_command('reject_pending_credentialing_applications',
                     number=settings.DEFAULT_NUMBER_OF_APPLICATIONS_TO_REJECT, stdout=out)

        # check if the applications are rejected
        if settings.ENABLE_CREDENTIALING_AUTO_REJECTION:
            for application in applications:
                application.refresh_from_db()
                # rejected applications should have status 1
                self.assertEqual(application.status, CredentialApplication.Status.REJECTED)

        else:
            LOGGER.info('Auto rejection of credentialing applications is disabled. Exiting.')
