from django.test import TestCase
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from user.models import AssociatedEmail, CredentialApplication, CredentialReview, User


class CredentialReferenceAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.applicant = User.objects.create_user(
            username='applicant', email='applicant@example.com',
            password='Tester11!', is_active=True,
            first_names='Alex', last_name='Applicant',
        )
        cls.reference = User.objects.create_user(
            username='reference', email='reference@example.com',
            password='Tester11!', is_active=True,
        )
        cls.other_user = User.objects.create_user(
            username='otheruser', email='other@example.com',
            password='Tester11!', is_active=True,
        )
        cls.application = CredentialApplication.objects.create(
            user=cls.applicant, slug='ref-account-test',
            first_names='Alex', last_name='Applicant',
            researcher_category=3,
            reference_name='Reference Person', reference_email='reference@example.com',
            reference_verification_token='reference-token',
        )
        CredentialReview.objects.create(application=cls.application, status=30)
        cls.url = reverse('credential_reference_verification', args=[
            cls.application.slug, cls.application.reference_verification_token,
        ])
        cls.old_url = reverse('credential_reference', args=[cls.application.slug])
        cls.response_data = {
            'reference_response': '2',
            'reference_response_text': 'I have worked with this applicant on the research.',
        }

    def test_anonymous_user_cannot_view_or_submit_response(self):
        for url in (self.url, self.old_url):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f'/login/?next={url}',
                                     fetch_redirect_response=False)
                self.assertRedirects(self.client.post(url, self.response_data),
                                     f'/login/?next={url}', fetch_redirect_response=False)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.reference_response_datetime)

    def test_wrong_account_cannot_view_or_submit_response(self):
        self.client.force_login(self.other_user)
        for url in (self.url, self.old_url):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, self.response_data).status_code, 403)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.reference_user)
        self.assertIsNone(self.application.reference_response_datetime)

    def test_unverified_invitation_address_cannot_respond(self):
        email = self.reference.get_primary_email()
        email.is_verified = False
        email.save()
        self.client.force_login(self.reference)
        response = self.client.post(self.url, self.response_data)
        self.assertEqual(response.status_code, 403)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.reference_response_datetime)

    def test_verified_secondary_address_can_respond(self):
        self.application.reference_email = 'alternate@example.com'
        self.application.save()
        AssociatedEmail.objects.create(
            user=self.reference, email='alternate@example.com', is_verified=True,
        )
        self.client.force_login(self.reference)
        response = self.client.post(self.url, self.response_data)
        self.assertEqual(response.status_code, 200)
        self.application.refresh_from_db()
        self.assertEqual(self.application.reference_user, self.reference)
        self.assertEqual(self.application.reference_response, 2)
        self.assertIsNotNone(self.application.reference_response_datetime)
        self.assertEqual(self.application.credential_review.status, 40)
        self.assertContains(self.client.get(self.url), 'A response has already been submitted.')

    def test_primary_address_can_respond_with_old_link(self):
        self.client.force_login(self.reference)
        response = self.client.post(self.old_url, self.response_data)
        self.assertEqual(response.status_code, 200)
        self.application.refresh_from_db()
        self.assertEqual(self.application.reference_user, self.reference)

    def test_invalid_token_does_not_accept_response(self):
        self.client.force_login(self.reference)
        url = reverse('credential_reference_verification', args=[self.application.slug, 'wrong-token'])
        self.assertRedirects(self.client.post(url, self.response_data), '/', fetch_redirect_response=False)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.reference_response_datetime)

    def test_second_response_cannot_overwrite_first(self):
        self.client.force_login(self.reference)
        with patch('user.views.process_credential_complete') as notify:
            first = self.client.post(self.url, {
                'reference_response': '1',
                'reference_response_text': 'I cannot support this request.',
            })
            second = self.client.post(self.url, self.response_data)
        self.assertEqual(first.status_code, 200)
        self.assertContains(second, 'A response has already been submitted.')
        notify.assert_called_once()
        self.application.refresh_from_db()
        self.assertEqual(self.application.reference_response, 1)
        self.assertEqual(self.application.reference_user, self.reference)

    def test_completed_request_is_explained_without_login(self):
        self.application.reference_response_datetime = timezone.now()
        self.application.save()
        for url in (self.url, self.old_url):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'A response has already been submitted.')
                self.assertContains(self.client.post(url, self.response_data),
                                    'A response has already been submitted.')
        self.application.refresh_from_db()
        self.assertEqual(self.application.reference_response, 0)
        self.assertIsNone(self.application.reference_user)

    def test_wrong_token_does_not_reveal_completed_request(self):
        self.application.reference_response_datetime = timezone.now()
        self.application.save()
        url = reverse('credential_reference_verification', args=[self.application.slug, 'wrong-token'])
        self.assertRedirects(self.client.get(url), '/', fetch_redirect_response=False)

    def test_closed_request_without_response_does_not_claim_it_was_answered(self):
        self.application.status = CredentialApplication.Status.WITHDRAWN
        self.application.save()
        self.assertRedirects(self.client.get(self.url), '/', fetch_redirect_response=False)

    def test_completed_response_uses_recorded_account_after_email_reassignment(self):
        self.application.reference_email = 'alternate@example.com'
        self.application.reference_user = self.reference
        self.application.reference_response_datetime = timezone.now()
        self.application.save()
        AssociatedEmail.objects.create(
            user=self.other_user, email='alternate@example.com', is_verified=True,
        )
        self.reference.is_credentialed = True
        self.reference.save()

        self.assertEqual(self.application.get_reference_user(), self.reference)
        self.assertTrue(self.application.ref_user_flag())
        self.assertTrue(self.application.ref_credentialed_flag())
        page = render_to_string('console/application_display_table.html', {
            'application': self.application, 'training_list': {},
        })
        self.assertIn('Responding account: <mark>reference</mark>', page)
        self.assertNotIn('Responding account: <mark>otheruser</mark>', page)

    def test_legacy_response_falls_back_to_invitation_email(self):
        self.reference.is_credentialed = True
        self.reference.save()
        self.application.reference_response_datetime = timezone.now()
        self.application.save()
        self.assertEqual(self.application.get_reference_user(), self.reference)
        self.assertTrue(self.application.ref_credentialed_flag())

    def test_reference_account_cannot_be_deleted_after_response(self):
        self.application.reference_user = self.reference
        self.application.save()
        deletable, reasons = self.reference.can_delete_account()
        self.assertFalse(deletable)
        self.assertIn('You have responded to a credential reference request.', reasons)
