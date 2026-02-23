import doctest
import json

from django.template import loader
from django.test import TestCase, Client
from django.conf import settings
from django.urls import reverse

from notification import utility
from notification.models import Notification, NotificationType
from notification.utility import create_notification
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


class TestNotificationModel(TestCase):
    fixtures = ['demo-project.json']

    def setUp(self):
        self.user = User.objects.get(username='george')
        self.actor = User.objects.get(username='rgmark')

    def test_create_notification(self):
        notif = create_notification(
            recipient=self.user,
            notification_type=NotificationType.AUTHOR_INVITATION,
            message='Test notification',
            url='/test/',
            actor=self.actor,
        )
        self.assertIsNotNone(notif)
        self.assertEqual(notif.recipient, self.user)
        self.assertEqual(notif.notification_type, NotificationType.AUTHOR_INVITATION)
        self.assertFalse(notif.is_read)

    def test_unread_count(self):
        for i in range(3):
            create_notification(
                recipient=self.user,
                notification_type=NotificationType.GENERIC,
                message=f'Notification {i}',
            )
        self.assertEqual(
            Notification.objects.filter(recipient=self.user, is_read=False).count(),
            3,
        )
        # Mark one as read
        n = Notification.objects.filter(recipient=self.user).first()
        n.is_read = True
        n.save()
        self.assertEqual(
            Notification.objects.filter(recipient=self.user, is_read=False).count(),
            2,
        )

    def test_str(self):
        notif = create_notification(
            recipient=self.user,
            notification_type=NotificationType.GENERIC,
            message='A short message',
        )
        self.assertIn('A short message', str(notif))


class TestNotificationViews(TestCase):
    fixtures = ['demo-project.json']

    def setUp(self):
        self.user = User.objects.get(username='george')
        self.other_user = User.objects.get(username='rgmark')
        self.client = Client()
        self.client.force_login(self.user)

    def test_notification_list_page(self):
        create_notification(
            recipient=self.user,
            notification_type=NotificationType.GENERIC,
            message='Test list notification',
        )
        response = self.client.get(reverse('notification_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test list notification')

    def test_notification_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('notification_list'))
        self.assertEqual(response.status_code, 302)

    def test_mark_notification_read(self):
        notif = create_notification(
            recipient=self.user,
            notification_type=NotificationType.GENERIC,
            message='Click me',
            url='/news/',
        )
        response = self.client.post(
            reverse('mark_notification_read', args=[notif.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/news/', response.url)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_notification_read_no_url(self):
        notif = create_notification(
            recipient=self.user,
            notification_type=NotificationType.GENERIC,
            message='No link',
        )
        response = self.client.post(
            reverse('mark_notification_read', args=[notif.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('notifications', response.url)

    def test_cannot_mark_other_users_notification(self):
        notif = create_notification(
            recipient=self.other_user,
            notification_type=NotificationType.GENERIC,
            message='Not yours',
        )
        response = self.client.post(
            reverse('mark_notification_read', args=[notif.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_mark_all_read(self):
        for i in range(3):
            create_notification(
                recipient=self.user,
                notification_type=NotificationType.GENERIC,
                message=f'Msg {i}',
            )
        self.client.post(reverse('mark_all_read'))
        self.assertEqual(
            Notification.objects.filter(recipient=self.user, is_read=False).count(),
            0,
        )

    def test_unread_count_json(self):
        for i in range(2):
            create_notification(
                recipient=self.user,
                notification_type=NotificationType.GENERIC,
                message=f'Msg {i}',
            )
        response = self.client.get(reverse('unread_count'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['unread_count'], 2)

    def test_mark_read_requires_post(self):
        notif = create_notification(
            recipient=self.user,
            notification_type=NotificationType.GENERIC,
            message='Test',
        )
        response = self.client.get(
            reverse('mark_notification_read', args=[notif.id])
        )
        self.assertEqual(response.status_code, 405)
