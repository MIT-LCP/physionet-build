import logging

from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

import notification.utility as notification

LOGGER = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        """
        Auto reject pending registration applications for events that are older than
        settings.MAX_EVENT_DAYS_BEFORE_AUTO_REJECTION
        """
        pass
