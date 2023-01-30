import logging

from django.core.management.base import BaseCommand

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        """
        Delete all Credentialing applications whose reference checks have Awaiting Reference Response pending after
        waiting for 1 month.
        """
        pass
