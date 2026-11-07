from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from notification.models import Notification, NotificationType
from project.models import ActiveProject, ReviewerAccessRequest, SubmissionStatus
from user.models import User
from user.test_views import TestMixin


class TestReviewerAccessRequests(TestMixin):
    """
    Authors can ask for a private reviewer link, and editors grant or
    decline the request from the console.
    """

    def setUp(self):
        super().setUp()
        self.project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.author = User.objects.get(username='rgmark')
        self.editor = User.objects.get(username='admin')
        self.project.submit(author_comments='')
        self.project.assign_editor(self.editor)
        mail.outbox.clear()

    def request_access(self, **data):
        self.client.login(username='rgmark', password='Tester11!')
        return self.client.post(reverse('project_submission', args=(self.project.slug,)), data={
            'request_reviewer_access': '',
            'journal': 'IEEE Transactions on Affective Computing',
            'hide_authors': 'False',
            'message': 'The manuscript is under review.',
            **data,
        })

    def respond(self, action, access_request, **data):
        self.client.login(username='admin', password='Tester11!')
        return self.client.post(reverse('submission_info', args=(self.project.slug,)), data={
            action: '',
            'access_request_id': access_request.id,
            **data,
        })

    def test_author_requests_access(self):
        response = self.request_access(hide_authors='True')
        self.assertRedirects(response, reverse('project_submission', args=(self.project.slug,)))

        access_request = self.project.revieweraccessrequests.get()
        self.assertTrue(access_request.is_active)
        self.assertTrue(access_request.hide_authors)
        self.assertEqual(access_request.requester, self.author)
        self.assertEqual(access_request.journal, 'IEEE Transactions on Affective Computing')

        # The editor is told by email and in the app
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.editor.email])
        self.assertIn('IEEE Transactions on Affective Computing', mail.outbox[0].body)
        self.assertTrue(Notification.objects.filter(
            recipient=self.editor, notification_type=NotificationType.REVIEWER_ACCESS).exists())

        # The author sees the pending request, and the editor sees it in the console
        response = self.client.get(reverse('project_submission', args=(self.project.slug,)))
        self.assertContains(response, 'Request pending')
        self.client.login(username='admin', password='Tester11!')
        response = self.client.get(reverse('submission_info', args=(self.project.slug,)))
        self.assertContains(response, 'Reviewer access requested')

    def test_only_one_pending_request(self):
        self.request_access()
        self.request_access()
        self.assertEqual(self.project.revieweraccessrequests.count(), 1)

    def test_cannot_request_before_submission(self):
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submission_status = SubmissionStatus.UNSUBMITTED
        project.save()
        self.request_access()
        self.assertFalse(ReviewerAccessRequest.objects.exists())

    def test_author_withdraws_request(self):
        self.request_access()
        self.client.post(reverse('project_submission', args=(self.project.slug,)),
                         data={'cancel_reviewer_access_request': ''})
        self.assertFalse(self.project.revieweraccessrequests.exists())

    def test_editor_grants_request(self):
        self.request_access()
        access_request = self.project.revieweraccessrequests.get()
        mail.outbox.clear()

        response = self.respond('grant_reviewer_access', access_request, link_type='masked')
        self.assertEqual(response.status_code, 200)

        access_request.refresh_from_db()
        self.assertFalse(access_request.is_active)
        self.assertTrue(access_request.response)
        self.assertEqual(access_request.responder, self.editor)

        anonymous = self.project.anonymous.get()
        self.assertTrue(anonymous.hide_authors)

        # The author receives a working link and passphrase
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.author.email])
        body = mail.outbox[0].body
        self.assertIn(reverse('anonymous_login', args=(anonymous.url,)), body)
        self.assertIn('no guarantee that it will be accepted', ' '.join(body.split()))
        passphrase = body.split('Passphrase: ')[1].split()[0]
        self.assertTrue(self.project.is_valid_passphrase(passphrase))

        # The author's page shows the active link but not the passphrase
        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.get(reverse('project_submission', args=(self.project.slug,)))
        self.assertContains(response, 'A reviewer link is active')
        self.assertContains(response, anonymous.url)
        self.assertNotContains(response, passphrase)

        # Answering the same request twice does nothing
        mail.outbox.clear()
        self.respond('grant_reviewer_access', access_request)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.project.anonymous.get().url, anonymous.url)

    def test_new_link_replaces_old_one(self):
        old_url, old_passphrase = self.project.generate_anonymous_access()
        anonymous = self.project.anonymous.get()
        anonymous.creation_datetime = timezone.now() - timedelta(days=365)
        anonymous.save()

        self.request_access()
        self.respond('grant_reviewer_access', self.project.revieweraccessrequests.get(), link_type='standard')

        anonymous = self.project.anonymous.get()
        self.assertNotEqual(anonymous.url, old_url)
        self.assertFalse(self.project.is_valid_passphrase(old_passphrase))
        # A replacement link gets a fresh validity period
        self.assertGreater(anonymous.expiry_datetime, timezone.now() + timedelta(days=179))

    def test_editor_declines_request(self):
        self.request_access()
        access_request = self.project.revieweraccessrequests.get()
        mail.outbox.clear()

        # A reason is required
        self.respond('decline_reviewer_access', access_request)
        access_request.refresh_from_db()
        self.assertTrue(access_request.is_active)

        self.respond('decline_reviewer_access', access_request,
                     response_message='Please contact us once the files are uploaded.')
        access_request.refresh_from_db()
        self.assertFalse(access_request.is_active)
        self.assertFalse(access_request.response)
        self.assertFalse(self.project.anonymous.exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('declined', mail.outbox[0].subject)
        self.assertIn('Please contact us once the files are uploaded.', mail.outbox[0].body)

        # The author sees the reason and can ask again
        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.get(reverse('project_submission', args=(self.project.slug,)))
        self.assertContains(response, 'was declined')
        self.assertContains(response, 'name="request_reviewer_access"')

    def test_non_editor_cannot_respond(self):
        self.request_access()
        access_request = self.project.revieweraccessrequests.get()
        self.client.login(username='rgmark', password='Tester11!')
        self.client.post(reverse('submission_info', args=(self.project.slug,)), data={
            'grant_reviewer_access': '',
            'access_request_id': access_request.id,
        })
        access_request.refresh_from_db()
        self.assertTrue(access_request.is_active)
        self.assertFalse(self.project.anonymous.exists())

    def test_expired_link_is_not_shown_as_active(self):
        self.project.generate_anonymous_access()
        anonymous = self.project.anonymous.get()
        anonymous.creation_datetime = timezone.now() - timedelta(days=365)
        anonymous.save()

        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.get(reverse('project_submission', args=(self.project.slug,)))
        self.assertContains(response, 'The previous reviewer link expired')
        self.assertNotContains(response, 'A reviewer link is active')

    def test_form_mentions_doi(self):
        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.get(reverse('project_submission', args=(self.project.slug,)))
        self.assertContains(response, 'A DOI is not assigned at this stage')
        self.assertContains(response, 'there is no guarantee that the')

    def test_only_submitting_author_can_request(self):
        co_author = User.objects.get(username='aewj')
        self.project.authors.create(user=co_author, display_order=self.project.authors.count() + 1)
        self.client.login(username='aewj', password='Tester11!')
        url = reverse('project_submission', args=(self.project.slug,))

        response = self.client.get(url)
        self.assertContains(response, 'Only the submitting author can request a reviewer link')
        self.assertNotContains(response, 'name="request_reviewer_access"')

        self.client.post(url, data={
            'request_reviewer_access': '',
            'journal': 'Some Journal',
            'hide_authors': 'False',
        })
        self.assertFalse(self.project.revieweraccessrequests.exists())

        # A co-author can see a pending request but cannot withdraw it
        self.request_access()
        self.client.login(username='aewj', password='Tester11!')
        response = self.client.get(url)
        self.assertContains(response, 'Request pending')
        self.assertNotContains(response, 'name="cancel_reviewer_access_request"')
        self.client.post(url, data={'cancel_reviewer_access_request': ''})
        self.assertTrue(self.project.revieweraccessrequests.filter(is_active=True).exists())
