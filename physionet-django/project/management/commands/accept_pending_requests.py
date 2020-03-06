"""
Command to:
- Accept pending requests of self managed projects
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

import notification.utility as notification
from project.models import DataAccessRequest
from user.models import User


class Command(BaseCommand):

    def handle(self, *args, **options):
        old_pending_rqs = DataAccessRequest.objects.filter(
            status=DataAccessRequest.PENDING_VALUE,
            request_datetime__lt=timezone.now() - timezone.timedelta(
                days=DataAccessRequest.DATA_ACCESS_REQUESTS_DAY_LIMIT))

        admin = User.objects.get(username='admin')

        for rq in old_pending_rqs:
            rq.status = DataAccessRequest.ACCEPT_REQUEST_VALUE
            rq.decision_datetime = timezone.now()
            rq.responder_id = admin.id
            rq.save()

            # TODO don't hardcode. how to get hostname to generate URL?
            notification.notify_user_data_access_request(rq, "https", "physionet.org")
