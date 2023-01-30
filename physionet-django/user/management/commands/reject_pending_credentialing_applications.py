import logging

from django.core.management.base import BaseCommand
from django.conf import settings

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        """
        Delete all Credentialing applications whose reference checks have Awaiting Reference Response pending after
        waiting for settings.MAX_REFERENCE_VERIFICATION_DAYS_BEFORE_AUTO_REJECTION days.
        """
        pass
