import logging
from io import StringIO

from django.conf import settings
from django.utils import timezone
from django.core.management import call_command

from user.management.commands import reject_pending_credentialing_applications
from user.models import CredentialApplication
from user.test_views import TestMixin

LOGGER = logging.getLogger(__name__)


def get_application_to_be_rejected():
    """
    Get all CredentialApplication that has been pending for more than
    settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION days.
    """
    today = timezone.now()
    limit = today - timezone.timedelta(days=settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION)

    # get all applications that have decision pending
    applications = CredentialApplication.objects.filter(status=0)
    # get applications with Reference Response pending
    response_applications = applications.filter(credential_review__status=30)
    # finally get applications that have been pending for more than the limit
    filtered_applications = response_applications.filter(reference_contact_datetime__lt=limit)
    return filtered_applications


class TestRejectPendingCredentialingApplications(TestMixin):

    def test_rejection(self):

        # load list of applications to be rejected
        applications = get_application_to_be_rejected()
        LOGGER.info(f'Found {len(applications)} applications to be rejected.')

        # call the management command to auto reject applications
        out = StringIO()
        call_command('reject_pending_credentialing_applications', number=10, stdout=out)

        # check if the applications are rejected
        for application in applications:
            application.refresh_from_db()
            # rejected applications should have status 1
            self.assertEqual(application.status, 1)

        applications = get_application_to_be_rejected()
        self.assertEqual(len(applications), 0)
