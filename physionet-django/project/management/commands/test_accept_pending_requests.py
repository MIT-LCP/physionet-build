from django.core import mail
from django.utils import timezone

from project.management.commands import accept_pending_requests
from project.models import DataAccessRequest, PublishedProject
from user.models import User
from user.test_views import TestMixin


class TestAcceptPendingRequests(TestMixin):

    def test_base(self):
        def get_req(user, days_delta):
            old_req = DataAccessRequest()

            project = PublishedProject.objects.get(
                title="Self Managed Access Database Demo")
            old_req.project = project
            old_req.requester = User.objects.get(username=user)
            old_req.status = DataAccessRequest.PENDING_VALUE

            old_req.save()
            old_req.request_datetime = timezone.now() - timezone.timedelta(
                days=days_delta)
            old_req.save()

        get_req('rgmark', 1)
        get_req('aewj', 30)

        # there are two access requests created above, plus one
        # predefined in demo-project.json
        self.assertEqual(DataAccessRequest.objects.count(), 3)
        self.assertEqual(DataAccessRequest.objects.filter(
            status=DataAccessRequest.PENDING_VALUE).count(), 3)

        accept_pending_requests.Command().handle()

        self.assertEqual(DataAccessRequest.objects.get(
            requester=User.objects.get(username='rgmark')).status,
                         DataAccessRequest.PENDING_VALUE)
        self.assertEqual(DataAccessRequest.objects.get(
            requester=User.objects.get(username='aewj')).status,
                         DataAccessRequest.ACCEPT_REQUEST_VALUE)

        # one of the two access requests above should be approved,
        # plus one from demo-project.json
        self.assertEqual(len(mail.outbox), 2)
