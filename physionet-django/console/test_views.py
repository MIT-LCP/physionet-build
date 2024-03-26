import json
import logging
import os
import pdb


import requests_mock
from background_task.tasks import tasks
from django.test.utils import get_runner
from django.urls import reverse
from events.models import EventAgreement
from project.models import (
    ActiveProject,
    Author,
    AuthorInvitation,
    License,
    PublishedProject,
    StorageRequest,
    SubmissionStatus,
)
from user.models import User
from physionet.models import FrontPageButton, StaticPage
from user.test_views import TestMixin, prevent_request_warnings

LOGGER = logging.getLogger(__name__)


class TestState(TestMixin):
    """
    Test that all objects are in their intended states, during and
    after review/publication state transitions.

    """

    PROJECT_TITLE = 'MIT-BIH Arrhythmia Database'
    PROJECT_SLUG = 'mitbih'
    EXAMPLE_FILE = 'subject-100/100.atr'
    AUTHOR = 'rgmark'
    AUTHOR_PASSWORD = 'Tester11!'
    EDITOR = 'admin'
    EDITOR_PASSWORD = 'Tester11!'

    def test_assign_editor(self):
        """
        Assign an editor
        """
        # Submit project
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        # Assign editor
        self.client.login(username='admin', password='Tester11!')
        editor = User.objects.get(username='amitupreti')
        response = self.client.post(reverse(
            'submitted_projects'), data={'project':project.id,
            'editor':editor.id})
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.assertTrue(project.editor, editor)
        self.assertEqual(project.submission_status, SubmissionStatus.NEEDS_DECISION)

    def test_reassign_editor(self):
        """
        Assign an editor, then reassign it
        """
        # Submit project
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        # Assign editor
        self.client.login(username='admin', password='Tester11!')
        editor = User.objects.get(username='cindyehlert')
        response = self.client.post(reverse('submitted_projects'), data={
            'project': project.id, 'editor': editor.id})
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.assertTrue(project.editor, editor)
        self.assertEqual(project.submission_status, SubmissionStatus.NEEDS_DECISION)

        # Reassign editor
        editor = User.objects.get(username='amitupreti')
        response = self.client.post(reverse('submission_info',
            args=(project.slug,)), data={'editor': editor.id})
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.assertTrue(project.editor, editor)

    def test_edit_reject(self):
        """
        Edit a project, rejecting it.
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        editor = User.objects.get(username='admin')
        project.assign_editor(editor)
        self.client.login(username='admin', password='Tester11!')
        # Reject submission
        response = self.client.post(reverse(
            'edit_submission', args=(project.slug,)), data={
            'soundly_produced':0, 'well_described':0, 'open_format':1,
            'data_machine_readable':0, 'reusable':1, 'no_phi':0,
            'pn_suitable':1, 'editor_comments':'Just bad.', 'decision':0
            })
        self.assertTrue(ActiveProject.objects.filter(slug=project.slug,
                                                     submission_status=SubmissionStatus.ARCHIVED))
        self.assertFalse(ActiveProject.objects.filter(slug=project.slug,
                                                      submission_status=SubmissionStatus.NEEDS_DECISION))

    def test_edit(self):
        """
        Edit a project. Request resubmission, then accept.
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        editor = User.objects.get(username='admin')
        project.assign_editor(editor)
        self.client.login(username='admin', password='Tester11!')
        # Revise with changes
        response = self.client.post(reverse(
            'edit_submission', args=(project.slug,)), data={
            'soundly_produced':1, 'well_described':1, 'open_format':1,
            'data_machine_readable':0, 'reusable':1, 'no_phi':0,
            'pn_suitable':1, 'editor_comments':'Remove the phi.', 'decision':1
            })
        project = ActiveProject.objects.get(id=project.id)
        self.assertTrue(project.author_editable())
        # Resubmit
        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.post(reverse(
            'project_submission', args=(project.slug,)),
            data={'resubmit_project':''})
        # Accept. All quality control fields must be True
        self.client.login(username='admin', password='Tester11!')
        response = self.client.post(reverse(
            'edit_submission', args=(project.slug,)), data={
            'soundly_produced':1, 'well_described':1, 'open_format':1,
            'data_machine_readable':0, 'reusable':1, 'no_phi':0,
            'pn_suitable':1, 'editor_comments':'Good.', 'decision':2
            })
        self.assertMessage(response, 40)
        response = self.client.post(
            reverse('edit_submission', args=(project.slug,)),
            data={
                'soundly_produced': 1,
                'well_described': 1,
                'open_format': 1,
                'data_machine_readable': 1,
                'reusable': 1,
                'no_phi': 1,
                'pn_suitable': 1,
                'editor_comments': 'Good.',
                'decision': 2,
                'ethics_included': 1,
            },
        )
        project = ActiveProject.objects.get(id=project.id)
        self.assertTrue(project.copyeditable())

    @prevent_request_warnings
    def test_copyedit(self):
        """
        Copyedit a project
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project.submit(author_comments='')
        editor = User.objects.get(username='admin')
        project.assign_editor(editor)
        self.client.login(username='admin', password='Tester11!')
        # Test that the editor cannot copyedit the content yet
        topic = project.topics.all().first()
        response = self.client.post(reverse(
            'edit_content_item', args=(project.slug,)), data={
            'item':'topic', 'remove_id':topic.id})
        self.assertEqual(response.status_code, 404)
        # Accept submission
        response = self.client.post(
            reverse('edit_submission', args=(project.slug,)),
            data={
                'soundly_produced': 1,
                'well_described': 1,
                'open_format': 1,
                'data_machine_readable': 1,
                'reusable': 1,
                'no_phi': 1,
                'pn_suitable': 1,
                'editor_comments': 'Good.',
                'decision': 2,
                'ethics_included': 1,
            },
        )
        # Copyedit project.
        # Remove a related item
        response = self.client.post(reverse(
            'edit_content_item', args=(project.slug,)), data={
            'item':'topic', 'remove_id':topic.id})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(project.topics.all().filter(id=topic.id))
        # Delete folders
        response = self.client.post(reverse(
            'copyedit_submission', args=(project.slug,)),
            data={'delete_items':'', 'subdir':'', 'items':['subject-100',
            'subject-101']})
        self.assertMessage(response, 25)
        self.assertFalse(os.path.isfile(os.path.join(project.file_root(),
            'subject-100')))
        # Complete copyedit
        response = self.client.post(reverse(
            'copyedit_submission', args=(project.slug,)),
            data={'complete_copyedit':'', 'made_changes':1,
            'changelog_summary':'Removed your things'})
        project = ActiveProject.objects.get(id=project.id)
        self.assertFalse(project.copyeditable())
        # Reopen copyedit
        response = self.client.post(reverse(
            'awaiting_authors', args=(project.slug,)),
            data={'reopen_copyedit':''})
        project = ActiveProject.objects.get(id=project.id)
        self.assertTrue(project.copyeditable())
        # Recomplete copyedit
        response = self.client.post(reverse(
            'copyedit_submission', args=(project.slug,)),
            data={'complete_copyedit':'', 'made_changes':1,
            'changelog_summary':'Removed your things'})
        project = ActiveProject.objects.get(id=project.id)
        self.assertFalse(project.copyeditable())

    def test_approve_publish(self):
        """
        Author approves publication
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')

        def get_project():
            return ActiveProject.objects.get(id=project.id)

        # The following steps should not alter the project timestamp,
        # since project "Metadata" fields are not being changed (only
        # "SubmissionInfo").
        timestamp = project.modified_datetime

        project.submit(author_comments='')
        self.assertEqual(get_project().modified_datetime, timestamp)

        editor = User.objects.get(username='admin')
        project.assign_editor(editor)
        self.assertEqual(get_project().modified_datetime, timestamp)

        self.client.login(username='admin', password='Tester11!')
        # Accept submission
        response = self.client.post(
            reverse('edit_submission', args=(project.slug,)),
            data={
                'soundly_produced': 1,
                'well_described': 1,
                'open_format': 1,
                'data_machine_readable': 1,
                'reusable': 1,
                'no_phi': 1,
                'pn_suitable': 1,
                'editor_comments': 'Good.',
                'decision': 2,
                'auto_doi': 1,
                'ethics_included': 1,
            },
        )
        self.assertEqual(get_project().modified_datetime, timestamp)

        # Complete copyedit
        response = self.client.post(reverse(
            'copyedit_submission', args=(project.slug,)),
            data={'complete_copyedit':'', 'made_changes':0})
        self.assertEqual(get_project().modified_datetime, timestamp)

        # Approve publication
        self.assertFalse(ActiveProject.objects.get(id=project.id).is_publishable())
        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.post(reverse(
            'project_submission', args=(project.slug,)),
            data={'approve_publication':''})
        self.assertEqual(get_project().modified_datetime, timestamp)

        self.assertTrue(ActiveProject.objects.get(id=project.id).is_publishable())

    def test_publish(self):
        """
        Test publishing project
        """
        # Get the project ready to publish
        self.test_approve_publish()
        self.client.login(username='admin', password='Tester11!')
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        project_slug = project.slug
        custom_slug = 'mitbih'

        # The project description includes links to internal files
        active_file_url = reverse('serve_active_project_file',
                                  args=(project.slug, 'RECORDS'))
        active_preview_url = reverse('display_active_project_file',
                                     args=(project.slug, 'RECORDS'))
        self.assertIn('href="{}"'.format(active_file_url),
                      project.usage_notes)
        self.assertIn('href="{}"'.format(active_preview_url),
                      project.usage_notes)

        # Try to publish with an already taken slug
        # (note that if the project is a new version,
        # publish_submission ignores the slug parameter)
        if not project.is_new_version:
            taken_slug = PublishedProject.objects.all().first().slug
            response = self.client.post(reverse(
                'publish_submission', args=(project.slug,)),
                data={'slug':taken_slug, 'doi': False, 'make_zip':1})
            self.assertTrue(bool(ActiveProject.objects.filter(
                slug=project_slug)))

        # Publish with a valid custom slug
        response = self.client.post(reverse(
            'publish_submission', args=(project.slug,)),
            data={'slug':custom_slug, 'doi': False, 'make_zip':1})

        # Run background tasks
        self.assertTrue(bool(tasks.run_next_task()))

        self.assertTrue(bool(PublishedProject.objects.filter(slug=custom_slug)))
        self.assertFalse(bool(PublishedProject.objects.filter(slug=project_slug)))
        self.assertFalse(bool(ActiveProject.objects.filter(slug=project_slug)))

        project = PublishedProject.objects.get(slug=custom_slug,
                                               version=project.version)
        # Access the published project's page and its (open) files
        response = self.client.get(reverse('published_project',
            args=(project.slug, project.version)))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('serve_published_project_file', args=(
            project.slug, project.version, 'subject-100/100.atr')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('serve_published_project_zip', args=(
            project.slug, project.version)))
        self.assertEqual(response.status_code, 200)
        # Access the submission log as the author
        self.client.login(username='rgmark', password='Tester11!')
        response = self.client.get(reverse('published_submission_history',
            args=(project.slug, project.version,)))
        self.assertEqual(response.status_code, 200)

        # The internal links should now point to published files
        self.assertNotIn('href="{}"'.format(active_file_url),
                         project.usage_notes)
        self.assertNotIn('href="{}"'.format(active_preview_url),
                         project.usage_notes)
        published_file_url = reverse('serve_published_project_file',
                                     args=(project.slug, project.version,
                                           'RECORDS'))
        published_preview_url = reverse('display_published_project_file',
                                        args=(project.slug, project.version,
                                              'RECORDS'))
        self.assertIn('href="{}"'.format(published_file_url),
                      project.usage_notes)
        self.assertIn('href="{}"'.format(published_preview_url),
                      project.usage_notes)

    def test_publish_with_versions(self):
        """
        Test publishing a project with multiple versions.
        """

        versions = ['1.0', '2.5', '2.10', '0.9']

        # Publish the initial project version (from fixture data)
        project = ActiveProject.objects.get(title=self.PROJECT_TITLE)
        project.version = versions[0]
        project.save()
        self.test_publish()
        project0 = PublishedProject.objects.get(slug=self.PROJECT_SLUG,
                                                version=versions[0])
        self.assertEqual(project0.version, versions[0])
        self.assertEqual(project0.version_order, 0)
        self.assertTrue(project0.is_latest_version)
        self.assertFalse(project0.has_other_versions)

        file_path0 = os.path.join(project0.file_root(), self.EXAMPLE_FILE)
        license_path0 = os.path.join(project0.file_root(), 'LICENSE.txt')
        sha256_path0 = os.path.join(project0.file_root(), 'SHA256SUMS.txt')
        self.assertTrue(os.path.isfile(file_path0))
        self.assertTrue(os.path.isfile(license_path0))
        self.assertTrue(os.path.isfile(sha256_path0))

        # Create new versions by copying the published version
        for version in versions[1:]:
            self.client.login(username=self.AUTHOR,
                              password=self.AUTHOR_PASSWORD)
            response = self.client.post(
                reverse('new_project_version', args=(self.PROJECT_SLUG,)),
                data={'version': version})
            self.test_publish()

        # Sort the list of version numbers
        sorted_versions = []
        for version in versions:
            sorted_versions.append([int(n) for n in version.split('.')])
        sorted_versions.sort()

        for (index, vnum) in enumerate(sorted_versions):
            version = '.'.join(str(n) for n in vnum)
            project = PublishedProject.objects.get(slug=self.PROJECT_SLUG,
                                                   version=version)
            self.assertEqual(project.version_order, index)
            if index == len(sorted_versions) - 1:
                self.assertTrue(project.is_latest_version)
            else:
                self.assertFalse(project.is_latest_version)
            self.assertTrue(project.has_other_versions)

            file_path = os.path.join(project.file_root(), self.EXAMPLE_FILE)
            license_path = os.path.join(project.file_root(), 'LICENSE.txt')
            sha256_path = os.path.join(project.file_root(), 'SHA256SUMS.txt')
            if version != versions[0]:
                self.assertTrue(os.path.samefile(file_path, file_path0))
                self.assertFalse(os.path.samefile(license_path, license_path0))
                self.assertFalse(os.path.samefile(sha256_path, sha256_path0))

    @requests_mock.Mocker()
    def test_publish_with_doi(self, mocker):
        """
        Test publishing a project while automatically assigning DOIs.
        """

        # Initial creation of draft DOIs
        # (console.utility.register_doi)
        mocker.post('https://api.datacite.example/dois', [
            {'text': json.dumps(
                {'data': {'attributes': {'doi': '10.0000/aaa'}}})},
            {'text': json.dumps(
                {'data': {'attributes': {'doi': '10.0000/bbb'}}})},
        ])

        # Checking status of DOIs when project is about to be
        # published (console.utility.get_doi_status)
        mocker.get('https://api.datacite.example/dois/10.0000/aaa', [
            {'text': json.dumps(
                {'data': {'attributes': {'state': 'draft'}}})},
        ])
        mocker.get('https://api.datacite.example/dois/10.0000/bbb', [
            {'text': json.dumps(
                {'data': {'attributes': {'state': 'draft'}}})},
        ])

        # Updating DOI state (console.utility.update_doi)
        mocker.put('https://api.datacite.example/dois/10.0000/aaa')
        mocker.put('https://api.datacite.example/dois/10.0000/bbb')

        with self.settings(
                DATACITE_API_URL='https://api.datacite.example/dois',
                DATACITE_USER='admin',
                DATACITE_PASSWORD='letmein',
                DATACITE_PREFIX='10.0000'):
            self.test_publish()

            project = PublishedProject.objects.get(slug='mitbih')
            self.assertEqual(project.doi, '10.0000/aaa')
            self.assertEqual(project.core_project.doi, '10.0000/bbb')

        self.assertEqual(mocker.call_count, 4)


class TestStaticPage(TestMixin):
    """ Test that all views are behaving as expected """

    def setUp(self):
        """ Login a test user and create a staticpage """

        super().setUp()
        self.client.login(username='admin', password='Tester11!')
        self.page_1 = StaticPage.objects.create(
            title="Testing Page 1", url="/about/page/testing/", nav_bar=True, nav_order=10)
        self.page_2 = StaticPage.objects.create(
            title="Testing Page 2", url="/about/page/testing/2/", nav_bar=True, nav_order=11)

    def test_static_page_add_get(self):
        """test the get verb"""

        response = self.client.get(reverse("static_page_add"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "console/static_page/add.html")

    def test_static_page_add_post_valid(self):
        """test the valid post verb"""

        static_page_count = StaticPage.objects.count()
        response = self.client.post(reverse("static_page_add"),
                                    {'title': "Testing Page", 'url': "/about/testing/",
                                    'nav_bar': False, 'nav_order': 50})
        self.assertRedirects(response, reverse("static_pages"), status_code=302)
        self.assertEqual(StaticPage.objects.count(), static_page_count + 1)

    def test_static_page_add_post_invalid(self):
        """test the invalid post verb"""

        response = self.client.post(reverse("static_page_add"),
                                    {'title': "Testing", 'url': "/testing/",
                                    'nav_bar': True, 'nav_order': 5})
        self.assertTemplateUsed(response, "console/static_page/add.html")

    def test_staticpage_button_ordering(self):
        """test the ordering post verb"""

        response = self.client.post(reverse("static_pages"), {'up': self.page_1.id, })
        self.assertRedirects(response, reverse("static_pages"), status_code=302)
        current_order = StaticPage.objects.get(id=self.page_1.id).nav_order
        self.assertEqual(current_order, self.page_1.nav_order - 1)

    def test_static_page_edit_get(self):
        """test the get verb"""

        response = self.client.get(reverse("static_page_edit",
                                           kwargs={'page_pk': self.page_1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "console/static_page/edit.html")

    def test_static_page_edit_post_valid(self):
        """test the valid post verb"""

        response = self.client.post(
            reverse("static_page_edit", args=(self.page_1.pk,)),
            {'title': "Testing", 'url': "/about/testing/page/", 'nav_bar': True, 'nav_order': 5}, follow=True)
        self.assertRedirects(response, reverse("static_pages"), status_code=302)

    def test_static_page_edit_post_invalid(self):
        """test the invalid post verb"""

        response = self.client.post(
            reverse("static_page_edit", args=(self.page_1.pk,)),
            {'title': "Testing", 'URL': "testing/", 'nav_bar': True, 'nav_order': 5})
        self.assertTemplateUsed(response, "console/static_page/edit.html")

    def test_static_page_delete(self):
        """test the delete view"""

        static_page_count = StaticPage.objects.count()
        response = self.client.post(
            reverse("static_page_delete", args=(self.page_1.pk,)), follow=True)
        self.assertRedirects(response, reverse("static_pages"), status_code=302)
        self.assertEqual(StaticPage.objects.count(), static_page_count - 1)


class TestFrontPageButton(TestMixin):
    """ Test that all views are behaving as expected """

    def setUp(self):
        """ Login a test user and create a frontpage button """

        super().setUp()
        self.client.login(username='admin', password='Tester11!')
        self.button_1 = FrontPageButton.objects.create(
            label="Testing Button", url="https://www.test.com", order=1)
        self.button_2 = FrontPageButton.objects.create(
            label="Testing Button 2", url="/about/test", order=2)

    def test_frontpage_button_add_get(self):
        """test the get verb"""

        response = self.client.get(reverse("frontpage_button_add"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "console/frontpage_button/add.html")

    def test_frontpage_button_add_post_valid(self):
        """test the valid post verb"""

        button_count = FrontPageButton.objects.count()
        response = self.client.post(reverse("frontpage_button_add"),
                                    {'label': "Google", 'url': "https://google.com",
                                    'order': 50})
        self.assertRedirects(response, reverse("frontpage_buttons"), status_code=302)
        self.assertEqual(FrontPageButton.objects.count(), button_count + 1)

    def test_frontpage_button_add_post_invalid(self):
        """test the invalid post verb"""

        response = self.client.post(reverse("frontpage_button_add"),
                                    {'label': "Testing", 'url': "testing/",
                                    'order': 5})
        self.assertTemplateUsed(response, "console/frontpage_button/add.html")

    def test_frontpage_button_ordering(self):
        """test the ordering post verb"""

        response = self.client.post(reverse("frontpage_buttons"),
                                    {'up': self.button_2.pk, })
        self.assertRedirects(response, reverse("frontpage_buttons"), status_code=302)
        current_order = FrontPageButton.objects.get(id=self.button_2.id).order
        self.assertEqual(current_order, self.button_2.order - 1)

    def test_frontpage_button_edit_get(self):
        """test the get verb"""

        response = self.client.get(
            reverse("frontpage_button_edit", args=(self.button_1.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "console/frontpage_button/edit.html")

    def test_frontpage_button_edit_post_valid(self):
        """test the valid post verb"""

        response = self.client.post(
            reverse("frontpage_button_edit", args=(self.button_1.pk,)),
            {'label': "Testing", 'url': "/about/testing/page/", 'order': 500}, follow=True)
        self.assertRedirects(response, reverse("frontpage_buttons"), status_code=302)

    def test_frontpage_button_edit_post_invalid(self):
        """test the invalid post verb"""

        response = self.client.post(
            reverse("frontpage_button_edit", args=(self.button_1.pk,)),
            {'label': "Testing", 'url': "testing/", 'order': 5})
        self.assertTemplateUsed(response, "console/frontpage_button/edit.html")

    def test_frontpage_button_delete(self):
        """test the delete view"""

        frontpage_button_count = FrontPageButton.objects.count()
        response = self.client.post(
            reverse("frontpage_button_delete", args=(self.button_1.pk,)), follow=True)
        self.assertRedirects(response, reverse("frontpage_buttons"), status_code=302)
        self.assertEqual(FrontPageButton.objects.count(), frontpage_button_count - 1)


class TestEventAgreements(TestMixin):
    """ Test that all views are behaving as expected """

    def setUp(self):
        """Setup for tests"""

        super().setUp()
        self.event_agreement_name = "test event agreement"
        self.event_agreement_version = "0.1"
        self.event_agreement_version_invalid = "1"
        self.event_agreement_version_new_version = "0.2"
        self.event_agreement_slug = "pyvo3g6nuc"
        self.event_agreement_slug_new_version = "a1b2c3d4e5"
        self.updated_event_agreement_name = "updated test event agreement"
        self.event_agreement_html_content = "<p>My test Event Agreement test content</p>"
        self.updated_event_agreement_html_content = "<p>My updated test Event Agreement test content</p>"
        self.event_agreement_access_template = "<p>My test Event Agreement test content</p>"

        self.client.login(username='admin', password='Tester11!')

    def test_add_event_agreement_valid(self):
        """tests the view that adds a valid event agreement"""

        # Create an event Agreement
        response = self.client.post(
            reverse('event_agreement_list'),
            data={
                'name': self.event_agreement_name,
                'version': self.event_agreement_version,
                'slug': self.event_agreement_slug,
                'is_active': True,
                'html_content': self.event_agreement_html_content,
                'access_template': self.event_agreement_access_template
            })
        self.assertEqual(response.status_code, 200)
        event_agreement = EventAgreement.objects.get(slug=self.event_agreement_slug)
        self.assertEqual(event_agreement.name, self.event_agreement_name)
        return event_agreement

    def test_add_event_agreement_invalid(self):
        """tests the view that adds an invalid event agreement"""

        # Try to Create an Invalid event Agreement
        response = self.client.post(
            reverse('event_agreement_list'),
            data={
                'name': self.event_agreement_name,
                'version': self.event_agreement_version_invalid,
                'slug': self.event_agreement_slug,
                'is_active': True,
                'html_content': self.event_agreement_html_content,
                'access_template': self.event_agreement_access_template
            })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'console/event_agreement_list.html')

    def test_edit_event_agreement_valid_1(self):
        """tests the view that edits name in event agreement"""

        event_agreement = self.test_add_event_agreement_valid()

        # Edit the event Agreement
        response = self.client.post(
            reverse('event_agreement_detail', args=[event_agreement.pk]),
            data={
                'name': self.updated_event_agreement_name,
                'version': self.event_agreement_version,
                'slug': self.event_agreement_slug,
                'is_active': True,
                'html_content': self.event_agreement_html_content,
                'access_template': self.event_agreement_access_template
            })

        self.assertEqual(response.status_code, 200)
        event_agreement = EventAgreement.objects.get(slug=self.event_agreement_slug)
        self.assertEqual(event_agreement.name, self.updated_event_agreement_name)

    def test_edit_event_agreement_valid_2(self):
        """tests the view that edits html_content in event agreement"""

        event_agreement = self.test_add_event_agreement_valid()

        # Edit the event Agreement
        response = self.client.post(
            reverse('event_agreement_detail', args=[event_agreement.pk]),
            data={
                'name': self.event_agreement_name,
                'version': self.event_agreement_version,
                'slug': self.event_agreement_slug,
                'is_active': True,
                'html_content': self.updated_event_agreement_html_content,
                'access_template': self.event_agreement_access_template
            })

        self.assertEqual(response.status_code, 200)
        event_agreement = EventAgreement.objects.get(slug=self.event_agreement_slug)
        self.assertEqual(event_agreement.html_content, self.updated_event_agreement_html_content)

    def test_edit_event_agreement_invalid_version(self):
        """tests the view that edits an invalid event agreement(invalid version)"""

        event_agreement = self.test_add_event_agreement_valid()

        # Edit the event Agreement
        response = self.client.post(
            reverse('event_agreement_detail', args=[event_agreement.pk]),
            data={
                'name': self.updated_event_agreement_name,
                'version': self.event_agreement_version_invalid,
                'slug': self.event_agreement_slug,
                'is_active': True,
                'html_content': self.event_agreement_html_content,
                'access_template': self.event_agreement_access_template
            })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'console/event_agreement_detail.html')

    def test_delete_event_agreement(self):
        """tests the view that deletes an event agreement"""

        event_agreement = self.test_add_event_agreement_valid()

        # Delete the event Agreement
        response = self.client.post(
            reverse('event_agreement_delete', args=[event_agreement.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(EventAgreement.objects.filter(slug=self.event_agreement_slug).exists(), False)

    def test_event_agreement_new_version_valid(self):
        """tests the view that adds a valid new version of event agreement"""

        event_agreement = self.test_add_event_agreement_valid()

        # Create an event Agreement
        response = self.client.post(
            reverse('event_agreement_new_version', args=[event_agreement.pk]),
            data={
                'name': self.event_agreement_name,
                'version': self.event_agreement_version_new_version,
                'slug': self.event_agreement_slug_new_version,
                'is_active': True,
                'html_content': self.event_agreement_html_content,
                'access_template': self.event_agreement_access_template
            })

        self.assertEqual(response.status_code, 302)
        event_agreement = EventAgreement.objects.get(slug=self.event_agreement_slug_new_version)
        self.assertEqual(event_agreement.version, self.event_agreement_version_new_version)

    def test_event_agreement_new_version_invalid_slug(self):
        """tests the view that adds an invalid new version of event agreement(invalid slug)"""

        event_agreement = self.test_add_event_agreement_valid()

        # Create an event Agreement
        response = self.client.post(
            reverse('event_agreement_new_version', args=[event_agreement.pk]),
            data={
                'name': self.event_agreement_name,
                'version': self.event_agreement_version_new_version,
                'slug': self.event_agreement_slug,
                'is_active': True,
                'html_content': self.event_agreement_html_content,
                'access_template': self.event_agreement_access_template
            })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'console/event_agreement_new_version.html')

    def test_event_agreement_new_version_invalid_version(self):
        """tests the view that adds an invalid new version of event agreement(invalid version)"""

        event_agreement = self.test_add_event_agreement_valid()

        # Create an event Agreement
        response = self.client.post(
            reverse('event_agreement_new_version', args=[event_agreement.pk]),
            data={
                'name': self.event_agreement_name,
                'version': self.event_agreement_version_invalid,
                'slug': self.event_agreement_slug_new_version,
                'is_active': True,
                'html_content': self.event_agreement_html_content,
                'access_template': self.event_agreement_access_template
            })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'console/event_agreement_new_version.html')
