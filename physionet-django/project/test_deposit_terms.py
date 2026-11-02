from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from physionet.models import Section, StaticPage
from project.models import (
    ActiveProject,
    Author,
    DepositTermsAcceptance,
    DepositTermsUnavailable,
    DepositTermsVersion,
    SubmissionStatus,
    UploadAgreement,
)
from user.models import User
from user.test_views import TestMixin

TERMS_URL = '/about/deposit-terms/'


@override_settings(DEPOSIT_TERMS_URL=TERMS_URL)
class TestDepositTerms(TestMixin):
    """
    Authors agree to the deposit terms when accepting the upload agreement
    and when approving publication.
    """

    def setUp(self):
        super().setUp()
        page = StaticPage.objects.create(title='Deposit Terms', url=TERMS_URL)
        self.section = Section.objects.create(
            static_page=page, title='1. You keep ownership', order=1,
            content='<p>You keep the copyright in your work.</p>')
        Section.objects.create(
            static_page=page, title='2. Publication is permanent', order=2,
            content='<p>Published projects are part of the scholarly record.</p>')

        self.project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.submitting_user = User.objects.get(username='rgmark')
        self.coauthor_user = User.objects.get(username='aewj')
        self.coauthor = Author.objects.create(
            project=self.project, user=self.coauthor_user, display_order=2)

    def make_awaiting_approval(self):
        project = self.project
        project.submission_status = SubmissionStatus.NEEDS_APPROVAL
        project.editor = User.objects.get(username='admin')
        project.copyedit_completion_datetime = timezone.now()
        project.save()

    def approve(self, user, on_behalf_of=None, accept=True):
        self.client.force_login(user)
        data = {'approve_publication': str(on_behalf_of.id) if on_behalf_of else ''}
        if accept:
            data['accept_deposit_terms'] = 'on'
        return self.client.post(
            reverse('project_submission', args=(self.project.slug,)), data=data, follow=True)

    def test_current_version_is_stored_once_per_text(self):
        version = DepositTermsVersion.current()
        self.assertIn('You keep the copyright in your work.', version.content)
        self.assertIn('<h2>2. Publication is permanent</h2>', version.content)
        self.assertEqual(DepositTermsVersion.current(), version)

        # Editing the page creates a new version
        self.section.content = '<p>You keep ownership of your work.</p>'
        self.section.save()
        new_version = DepositTermsVersion.current()
        self.assertNotEqual(new_version, version)
        self.assertEqual(DepositTermsVersion.objects.count(), 2)

    @override_settings(DEPOSIT_TERMS_URL='/about/missing/')
    def test_missing_page_is_unavailable(self):
        with self.assertRaises(DepositTermsUnavailable):
            DepositTermsVersion.current()

    def test_upload_agreement_requires_terms(self):
        # Check the agreement itself, since upload_agreement_accepted() is
        # always true for projects created before UPLOAD_AGREEMENT_START_DATE
        submitting_author = self.project.submitting_author()
        UploadAgreement.objects.filter(author=submitting_author).delete()
        url = reverse('project_upload_agreement', args=(self.project.slug,))
        self.client.force_login(self.submitting_user)

        response = self.client.get(url)
        self.assertContains(response, 'You keep the copyright in your work.')
        self.assertContains(response, 'I have read and agree to the Deposit Terms.')

        # Without agreeing to the terms
        response = self.client.post(url, data={
            'no_human_subjects': 'on', 'deposit_terms_version': version_id})
        self.assertContains(response, 'Please agree to the Deposit Terms.')
        self.assertFalse(UploadAgreement.objects.filter(author=submitting_author).exists())
        self.assertFalse(DepositTermsAcceptance.for_project(self.project).exists())

        # Agreeing to the terms
        self.client.post(url, data={'no_human_subjects': 'on', 'accept_deposit_terms': 'on'})
        self.assertTrue(UploadAgreement.objects.get(author=submitting_author).accepted)
        acceptance = DepositTermsAcceptance.for_project(self.project).get()
        self.assertEqual(acceptance.stage, DepositTermsAcceptance.Stage.UPLOAD)
        self.assertEqual(acceptance.author_user, self.submitting_user)
        self.assertEqual(acceptance.accepted_by, self.submitting_user)
        self.assertFalse(acceptance.on_behalf)
        self.assertEqual(acceptance.terms_version, DepositTermsVersion.current())

    def test_approval_requires_terms(self):
        self.make_awaiting_approval()

        response = self.approve(self.submitting_user, accept=False)
        self.assertContains(response, 'Please agree to the Deposit Terms to approve publication.')
        self.assertIsNone(self.project.authors.get(user=self.submitting_user).approval_datetime)

        response = self.approve(self.submitting_user)
        self.assertContains(response, 'You have approved the project for publication.')
        self.assertIsNotNone(self.project.authors.get(user=self.submitting_user).approval_datetime)
        acceptance = DepositTermsAcceptance.for_project(self.project).get()
        self.assertEqual(acceptance.stage, DepositTermsAcceptance.Stage.APPROVAL)
        self.assertEqual(acceptance.author_user, self.submitting_user)
        self.assertEqual(len(mail.outbox), 0)

    def test_approval_page_shows_terms(self):
        self.make_awaiting_approval()
        self.client.force_login(self.submitting_user)
        response = self.client.get(reverse('project_submission', args=(self.project.slug,)))
        self.assertContains(response, 'name="accept_deposit_terms"', count=2)
        self.assertContains(response, f'I confirm that {self.coauthor_user.get_full_name()} has reviewed')

    def test_approval_on_behalf_is_recorded_and_notified(self):
        self.make_awaiting_approval()
        self.approve(self.submitting_user, on_behalf_of=self.coauthor)

        self.assertIsNotNone(Author.objects.get(id=self.coauthor.id).approval_datetime)
        acceptance = DepositTermsAcceptance.for_project(self.project).get()
        self.assertEqual(acceptance.author_user, self.coauthor_user)
        self.assertEqual(acceptance.accepted_by, self.submitting_user)
        self.assertTrue(acceptance.on_behalf)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.coauthor_user.email])
        body = ' '.join(mail.outbox[0].body.split())
        self.assertIn('on your behalf', body)
        self.assertIn('If this is not correct, please contact the editor', body)
        self.assertIn(TERMS_URL, body)

    def test_publication_needs_every_author_to_agree(self):
        self.make_awaiting_approval()
        self.approve(self.submitting_user)

        # The co-author's approval is recorded without the terms (for
        # example, by an older version of the site)
        self.project.approve_author(Author.objects.get(id=self.coauthor.id))
        self.assertEqual(self.project.authors_missing_deposit_terms(),
                         [Author.objects.get(id=self.coauthor.id)])
        self.assertFalse(self.project.is_publishable())

        # Approvals from before the terms were first shown are not counted
        DepositTermsVersion.objects.update(created_datetime=timezone.now())
        self.assertEqual(self.project.authors_missing_deposit_terms(), [])

    def test_agreements_from_before_copyedit_was_reopened_do_not_count(self):
        self.make_awaiting_approval()
        self.approve(self.submitting_user)
        self.approve(self.submitting_user, on_behalf_of=self.coauthor)
        self.assertEqual(self.project.authors_missing_deposit_terms(), [])

        # The editor reopens the copyedit, and the authors approve again
        # without agreeing to the terms
        self.project = ActiveProject.objects.get(id=self.project.id)
        self.project.reopen_copyedit()
        self.make_awaiting_approval()
        for author in self.project.authors.all():
            self.project.approve_author(author)
        self.assertEqual(len(self.project.authors_missing_deposit_terms()), 2)

    @override_settings(DEPOSIT_TERMS_URL='/about/missing/')
    def test_approval_refused_when_terms_unavailable(self):
        self.make_awaiting_approval()
        with self.assertLogs('project.views', level='ERROR'):
            response = self.approve(self.submitting_user)
        self.assertContains(response, 'The Deposit Terms are unavailable.')
        self.assertIsNone(self.project.authors.get(user=self.submitting_user).approval_datetime)

    @override_settings(DEPOSIT_TERMS_URL=None)
    def test_nothing_changes_when_turned_off(self):
        self.make_awaiting_approval()
        self.client.force_login(self.submitting_user)
        response = self.client.get(reverse('project_submission', args=(self.project.slug,)))
        self.assertNotContains(response, 'accept_deposit_terms')

        self.approve(self.submitting_user, accept=False)
        self.approve(self.submitting_user, on_behalf_of=self.coauthor, accept=False)
        self.assertTrue(self.project.all_authors_approved())
        self.assertFalse(DepositTermsAcceptance.objects.exists())
        self.assertEqual(self.project.authors_missing_deposit_terms(), [])
        # Only the usual "all authors approved" emails are sent
        self.assertTrue(mail.outbox)
        self.assertFalse([m for m in mail.outbox if 'on your behalf' in m.subject])

    def test_console_shows_agreements(self):
        self.make_awaiting_approval()
        self.approve(self.submitting_user, on_behalf_of=self.coauthor)
        acceptance = DepositTermsAcceptance.objects.get()

        self.client.force_login(User.objects.get(username='admin'))
        response = self.client.get(reverse('submission_info', args=(self.project.slug,)))
        self.assertContains(response, 'Deposit Terms:')
        self.assertContains(response, 'On behalf')
        version_url = reverse('deposit_terms_version', args=(acceptance.terms_version_id,))
        self.assertContains(response, version_url)

        response = self.client.get(version_url)
        self.assertContains(response, 'You keep the copyright in your work.')
        self.assertContains(response, acceptance.terms_version.content_hash)

        # Authors can't see the console page
        self.client.force_login(self.submitting_user)
        response = self.client.get(version_url)
        self.assertNotEqual(response.status_code, 200)

    def test_static_page_editor_warns_about_changes(self):
        self.client.force_login(User.objects.get(username='admin'))
        page = StaticPage.objects.get(url=TERMS_URL)
        response = self.client.get(reverse('static_page_sections', args=(page.id,)))
        self.assertContains(response, 'Changes apply only to future agreements')
