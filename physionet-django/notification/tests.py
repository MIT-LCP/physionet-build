import doctest
import io
import json
import os
import shutil

from PIL import Image

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import loader
from django.test import TestCase, Client, override_settings
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


def _make_image_bytes(fmt='PNG', size=(1, 1)):
    """Create minimal valid image bytes in the given format."""
    buf = io.BytesIO()
    Image.new('RGB', size).save(buf, format=fmt)
    return buf.getvalue()


TEST_MEDIA_ROOT = os.path.join(settings.BASE_DIR, 'test_media_news_upload')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class TestNewsImageUpload(TestCase):
    fixtures = ['demo-project.json']

    url = reverse('news_image_upload')

    def setUp(self):
        self.staff_user = User.objects.get(username='admin')
        self.regular_user = User.objects.get(username='george')
        self.client = Client()

    def tearDown(self):
        if os.path.exists(TEST_MEDIA_ROOT):
            shutil.rmtree(TEST_MEDIA_ROOT)

    # ---- auth / method tests ----

    def test_anonymous_user_forbidden(self):
        image = SimpleUploadedFile('test.png', _make_image_bytes(), content_type='image/png')
        response = self.client.post(self.url, {'file': image})
        self.assertEqual(response.status_code, 403)

    def test_regular_user_forbidden(self):
        self.client.force_login(self.regular_user)
        image = SimpleUploadedFile('test.png', _make_image_bytes(), content_type='image/png')
        response = self.client.post(self.url, {'file': image})
        self.assertEqual(response.status_code, 403)

    def test_get_not_allowed(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    # ---- validation tests ----

    def test_no_file_returns_400(self):
        self.client.force_login(self.staff_user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('No file', response.json()['error'])

    def test_invalid_file_returns_400(self):
        self.client.force_login(self.staff_user)
        bad_file = SimpleUploadedFile('evil.exe', b'MZ\x90\x00not-an-image', content_type='application/octet-stream')
        response = self.client.post(self.url, {'file': bad_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid image', response.json()['error'])

    def test_fake_content_type_rejected(self):
        """A non-image file with a spoofed image Content-Type is rejected."""
        self.client.force_login(self.staff_user)
        bad_file = SimpleUploadedFile('fake.png', b'not-image-data', content_type='image/png')
        response = self.client.post(self.url, {'file': bad_file})
        self.assertEqual(response.status_code, 400)

    def test_oversized_file_returns_400(self):
        self.client.force_login(self.staff_user)
        # 6 MB of data with a valid PNG header won't pass size check before Pillow
        big_file = SimpleUploadedFile('big.png', b'\x00' * (6 * 1024 * 1024), content_type='image/png')
        response = self.client.post(self.url, {'file': big_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn('too large', response.json()['error'])

    def test_unsupported_format_returns_400(self):
        """A valid image in an unsupported format (BMP) is rejected."""
        self.client.force_login(self.staff_user)
        bmp_bytes = _make_image_bytes(fmt='BMP')
        bmp_file = SimpleUploadedFile('test.bmp', bmp_bytes, content_type='image/bmp')
        response = self.client.post(self.url, {'file': bmp_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Unsupported', response.json()['error'])

    # ---- happy path tests ----

    def test_upload_png(self):
        self.client.force_login(self.staff_user)
        image = SimpleUploadedFile('photo.png', _make_image_bytes('PNG'), content_type='image/png')
        response = self.client.post(self.url, {'file': image})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('location', data)
        self.assertTrue(data['location'].startswith(settings.MEDIA_URL))
        self.assertTrue(data['location'].endswith('.png'))

    def test_upload_jpeg(self):
        self.client.force_login(self.staff_user)
        image = SimpleUploadedFile('photo.jpg', _make_image_bytes('JPEG'), content_type='image/jpeg')
        response = self.client.post(self.url, {'file': image})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['location'].endswith('.jpg'))

    def test_upload_gif(self):
        self.client.force_login(self.staff_user)
        image = SimpleUploadedFile('anim.gif', _make_image_bytes('GIF'), content_type='image/gif')
        response = self.client.post(self.url, {'file': image})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['location'].endswith('.gif'))

    def test_upload_webp(self):
        self.client.force_login(self.staff_user)
        image = SimpleUploadedFile('photo.webp', _make_image_bytes('WEBP'), content_type='image/webp')
        response = self.client.post(self.url, {'file': image})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['location'].endswith('.webp'))

    def test_file_written_to_disk(self):
        self.client.force_login(self.staff_user)
        image_data = _make_image_bytes('PNG')
        image = SimpleUploadedFile('disk.png', image_data, content_type='image/png')
        response = self.client.post(self.url, {'file': image})
        self.assertEqual(response.status_code, 200)

        location = response.json()['location']
        relative_path = location.replace(settings.MEDIA_URL, '', 1)
        filepath = os.path.join(TEST_MEDIA_ROOT, relative_path)
        self.assertTrue(os.path.isfile(filepath))
        with open(filepath, 'rb') as f:
            self.assertEqual(f.read(), image_data)
