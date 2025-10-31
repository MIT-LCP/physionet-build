import doctest

from django.template import loader
from django.test import TestCase
from django.conf import settings

from notification import utility
from project.models import DataAccessRequest, PublishedProject
from user.models import User

# Automatically run documentation tests in these modules.
DOCTEST_MODULES = [
    utility,
]

DOCTEST_FLAGS = doctest.REPORT_NDIFF


def load_tests(loader, tests, ignore):
    for module in DOCTEST_MODULES:
        tests.addTests(doctest.DocTestSuite(module, optionflags=DOCTEST_FLAGS))
    return tests


class TestDataAccessRequestNotification(TestCase):
    """
    Test that data access request notification emails contain correct URLs.
    """
    fixtures = ['demo-project.json']

    def test_notify_owner_data_access_request_url(self):
        """
        Test that the notification email contains the correct URL with
        data_access_request.id (not requester.id).
        """
        owner = User.objects.get(username='george')
        requester = User.objects.get(username='rgmark')
        project = PublishedProject.objects.get(title="Self Managed Access Database Demo")

        # Dummy DataAccessRequest to avoid ID collision with rgmark
        DataAccessRequest.objects.create(
            requester=requester,
            project=project,
            data_use_title='Dummy Request',
            data_use_purpose='Dummy purposes',
            status=DataAccessRequest.PENDING_VALUE
        )

        dar = DataAccessRequest.objects.create(
            requester=requester,
            project=project,
            data_use_title='Test Request',
            data_use_purpose='Testing purposes',
            status=DataAccessRequest.PENDING_VALUE
        )

        # Ensure the IDs are different
        self.assertNotEqual(dar.id, requester.id,
                            "Test setup error: DataAccessRequest ID should differ from requester ID")

        body = loader.render_to_string(
            'notification/email/notify_owner_data_access_request.html', {
                'user': owner,
                'data_access_request': dar,
                'signature': settings.EMAIL_SIGNATURE,
                'request_host': 'example.com',
                'request_protocol': 'https'
            })

        expected_url_path = f'/access-requests/{project.slug}/{project.version}/{dar.id}/'
        wrong_url_path = f'/access-requests/{project.slug}/{project.version}/{requester.id}/'

        self.assertIn(expected_url_path, body,
                      f"Email should contain correct URL with DataAccessRequest ID {dar.id}")
        self.assertNotIn(wrong_url_path, body,
                         f"Email should not contain wrong URL with requester ID {requester.id}")
