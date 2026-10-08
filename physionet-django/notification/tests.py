import doctest
import io
import json
import os
import shutil
import uuid

from django.contrib.auth.models import Permission
from django.template import loader
from django.test import TestCase, Client, override_settings
from django.conf import settings
from django.urls import reverse
from PIL import Image

from notification import utility
from notification.models import News, Notification, NotificationType
from notification.utility import create_notification
from project.models import DataAccessRequest, PublishedProject
from user.models import User

TEST_MEDIA_ROOT = os.path.join(settings.BASE_DIR, 'test_media_news_upload')

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


def _make_test_image(fmt='PNG', size=(10, 10)):
    """Create an in-memory image file for testing."""
    buf = io.BytesIO()
    img = Image.new('RGB', size, color='red')
    img.save(buf, format=fmt)
    buf.seek(0)
    buf.name = f'test.{fmt.lower()}'
    return buf


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class TestNewsImageUpload(TestCase):
    fixtures = ['demo-user.json']

    def setUp(self):
        self.admin_user = User.objects.get(username='admin')
        perm = Permission.objects.get(codename='change_news')
        self.admin_user.user_permissions.add(perm)
        self.regular_user = User.objects.get(username='rgmark')
        self.client = Client()
        self.guid = str(uuid.uuid4())
        self.upload_url = reverse('news_image_upload') + f'?guid={self.guid}'

    def tearDown(self):
        if os.path.isdir(TEST_MEDIA_ROOT):
            shutil.rmtree(TEST_MEDIA_ROOT)

    def test_anonymous_user_forbidden(self):
        img = _make_test_image()
        response = self.client.post(self.upload_url, {'file': img})
        self.assertEqual(response.status_code, 403)

    def test_regular_user_forbidden(self):
        self.client.force_login(self.regular_user)
        img = _make_test_image()
        response = self.client.post(self.upload_url, {'file': img})
        self.assertEqual(response.status_code, 403)

    def test_get_not_allowed(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(self.upload_url)
        self.assertEqual(response.status_code, 405)

    def test_missing_guid_returns_400(self):
        self.client.force_login(self.admin_user)
        img = _make_test_image()
        url = reverse('news_image_upload')
        response = self.client.post(url, {'file': img})
        self.assertEqual(response.status_code, 400)

    def test_invalid_guid_returns_400(self):
        self.client.force_login(self.admin_user)
        img = _make_test_image()
        url = reverse('news_image_upload') + '?guid=not-a-uuid'
        response = self.client.post(url, {'file': img})
        self.assertEqual(response.status_code, 400)

    def test_no_file_returns_400(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(self.upload_url)
        self.assertEqual(response.status_code, 400)

    def test_invalid_file_returns_400(self):
        self.client.force_login(self.admin_user)
        fake = io.BytesIO(b'not an image')
        fake.name = 'test.png'
        response = self.client.post(self.upload_url, {'file': fake})
        self.assertEqual(response.status_code, 400)

    def test_fake_content_type_rejected(self):
        self.client.force_login(self.admin_user)
        fake = io.BytesIO(b'GIF89a' + b'\x00' * 100)
        fake.name = 'test.gif'
        response = self.client.post(self.upload_url, {'file': fake})
        self.assertEqual(response.status_code, 400)

    def test_oversized_file_returns_400(self):
        self.client.force_login(self.admin_user)
        buf = io.BytesIO()
        # Create image with enough pixel data to exceed 5 MB
        img = Image.new('RGB', (2000, 2000), color='red')
        img.save(buf, format='BMP')
        buf.seek(0)
        buf.name = 'big.bmp'
        self.assertGreater(buf.getbuffer().nbytes, 5 * 1024 * 1024)
        response = self.client.post(self.upload_url, {'file': buf})
        self.assertEqual(response.status_code, 400)

    def test_unsupported_format_returns_400(self):
        self.client.force_login(self.admin_user)
        buf = io.BytesIO()
        img = Image.new('RGB', (10, 10), color='red')
        img.save(buf, format='TIFF')
        buf.seek(0)
        buf.name = 'test.tiff'
        response = self.client.post(self.upload_url, {'file': buf})
        self.assertEqual(response.status_code, 400)

    def test_upload_png(self):
        self.client.force_login(self.admin_user)
        img = _make_test_image('PNG')
        response = self.client.post(self.upload_url, {'file': img})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('location', data)
        self.assertTrue(data['location'].startswith(f'/news/images/{self.guid}/'))
        self.assertTrue(data['location'].endswith('.png'))

    def test_upload_jpeg(self):
        self.client.force_login(self.admin_user)
        img = _make_test_image('JPEG')
        response = self.client.post(self.upload_url, {'file': img})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['location'].endswith('.jpg'))

    def test_upload_gif(self):
        self.client.force_login(self.admin_user)
        img = _make_test_image('GIF')
        response = self.client.post(self.upload_url, {'file': img})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['location'].endswith('.gif'))

    def test_upload_webp(self):
        self.client.force_login(self.admin_user)
        img = _make_test_image('WEBP')
        response = self.client.post(self.upload_url, {'file': img})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['location'].endswith('.webp'))

    def test_file_written_to_disk(self):
        self.client.force_login(self.admin_user)
        img = _make_test_image('PNG')
        response = self.client.post(self.upload_url, {'file': img})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Extract filename from location
        filename = data['location'].split('/')[-1]
        filepath = os.path.join(
            TEST_MEDIA_ROOT, 'news', self.guid, 'images', filename
        )
        self.assertTrue(os.path.isfile(filepath))


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class TestNewsImageServing(TestCase):
    fixtures = ['demo-user.json']

    def setUp(self):
        self.guid = str(uuid.uuid4())
        self.filename = 'testimage.png'
        image_dir = os.path.join(
            TEST_MEDIA_ROOT, 'news', self.guid, 'images'
        )
        os.makedirs(image_dir, exist_ok=True)
        # Create a real PNG file
        img = Image.new('RGB', (10, 10), color='blue')
        img.save(os.path.join(image_dir, self.filename))

    def tearDown(self):
        if os.path.isdir(TEST_MEDIA_ROOT):
            shutil.rmtree(TEST_MEDIA_ROOT)

    def test_serve_existing_image(self):
        url = reverse('news_image', kwargs={
            'guid': self.guid, 'filename': self.filename
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_404_for_missing_image(self):
        url = reverse('news_image', kwargs={
            'guid': self.guid, 'filename': 'nonexistent.png'
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_404_for_invalid_guid(self):
        url = reverse('news_image', kwargs={
            'guid': 'not-a-uuid', 'filename': self.filename
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class TestOrphanCleanup(TestCase):
    fixtures = ['demo-user.json']

    def setUp(self):
        self.admin_user = User.objects.get(username='admin')
        perm = Permission.objects.get(codename='change_news')
        self.admin_user.user_permissions.add(perm)
        self.client = Client()
        self.client.force_login(self.admin_user)

    def tearDown(self):
        if os.path.isdir(TEST_MEDIA_ROOT):
            shutil.rmtree(TEST_MEDIA_ROOT)

    def test_orphaned_directory_cleaned_on_form_load(self):
        orphan_guid = str(uuid.uuid4())
        orphan_dir = os.path.join(TEST_MEDIA_ROOT, 'news', orphan_guid)
        os.makedirs(os.path.join(orphan_dir, 'images'), exist_ok=True)
        self.assertTrue(os.path.isdir(orphan_dir))

        self.client.get(reverse('news_add'))
        self.assertFalse(os.path.isdir(orphan_dir))

    def test_non_orphaned_directory_preserved(self):
        news = News.objects.create(
            title='Test', slug='test-preserve', content='<p>Test</p>'
        )
        news_dir = os.path.join(TEST_MEDIA_ROOT, 'news', str(news.guid))
        os.makedirs(os.path.join(news_dir, 'images'), exist_ok=True)

        self.client.get(reverse('news_add'))
        self.assertTrue(os.path.isdir(news_dir))

    def test_delete_news_removes_images(self):
        news = News.objects.create(
            title='Test Delete', slug='test-delete', content='<p>Test</p>'
        )
        news_dir = os.path.join(TEST_MEDIA_ROOT, 'news', str(news.guid))
        os.makedirs(os.path.join(news_dir, 'images'), exist_ok=True)
        # Create a dummy image file
        img = Image.new('RGB', (10, 10), color='red')
        img.save(os.path.join(news_dir, 'images', 'test.png'))
        self.assertTrue(os.path.isdir(news_dir))

        self.client.post(
            reverse('news_edit', kwargs={'news_slug': 'test-delete'}),
            {'delete': '1'}
        )
        self.assertFalse(os.path.isdir(news_dir))

    def test_saved_news_images_survive_cleanup(self):
        """
        Upload an image during news creation, save, then load news_add
        again. The saved news item's image directory must not be deleted.
        """
        # Load the add form to get the guid from the hidden field
        response = self.client.get(reverse('news_add'))
        form = response.context['form']
        guid = form._form_guid

        # Upload an image using this guid
        upload_url = reverse('news_image_upload') + f'?guid={guid}'
        img = _make_test_image('PNG')
        upload_resp = self.client.post(upload_url, {'file': img})
        self.assertEqual(upload_resp.status_code, 200)
        location = upload_resp.json()['location']

        # Save the news item, passing the guid via the hidden field
        self.client.post(reverse('news_add'), {
            'slug': 'image-test',
            'title': 'Image Test',
            'content': f'<p><img src="{location}"></p>',
            'url': '',
            'news_guid': guid,
        })
        news = News.objects.get(slug='image-test')
        self.assertEqual(str(news.guid), guid)

        # Verify image directory exists
        image_dir = os.path.join(TEST_MEDIA_ROOT, 'news', guid)
        self.assertTrue(os.path.isdir(image_dir))

        # Load news_add again (triggers orphan cleanup)
        self.client.get(reverse('news_add'))

        # The saved news item's images must still be there
        self.assertTrue(os.path.isdir(image_dir))
