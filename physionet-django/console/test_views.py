import json
import logging
import os
import pdb


import requests_mock
from django.contrib.sites.models import Site
from django.test import TestCase
from django.test.utils import get_runner
from django.urls import reverse
from events.models import EventAgreement
from project.models import (
    ActiveProject,
    AnonymousAccess,
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
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        editor = User.objects.get(username='amitupreti')

        # Add editor as a project author
        temp_author = project.authors.create(
            user=editor,
            display_order=project.authors.count() + 1,
        )
        temp_author.affiliations.create(name='MIT')

        # Submit project
        self.assertTrue(project.is_submittable())
        project.submit(author_comments='')
        self.assertIsNone(project.editor)
        self.assertEqual(project.submission_status, SubmissionStatus.NEEDS_ASSIGNMENT)

        # Try to assign editor; this should fail
        self.client.login(username='admin', password='Tester11!')
        self.client.post(reverse('submitted_projects'), data={
            'assign_editor': '',
            'project': project.id,
            'editor': editor.id,
        })
        project.refresh_from_db()
        self.assertIsNone(project.editor)
        self.assertEqual(project.submission_status, SubmissionStatus.NEEDS_ASSIGNMENT)

        # Remove author and try to assign again
        temp_author.delete()
        self.client.login(username='admin', password='Tester11!')
        self.client.post(reverse('submitted_projects'), data={
            'assign_editor': '',
            'project': project.id,
            'editor': editor.id,
        })
        project.refresh_from_db()
        self.assertEqual(project.editor, editor)
        self.assertEqual(project.submission_status, SubmissionStatus.NEEDS_DECISION)

    def test_reassign_editor(self):
        """
        Assign an editor, then reassign it
        """
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        editor1 = User.objects.get(username='cindyehlert')
        editor2 = User.objects.get(username='amitupreti')

        # Add editor2 as a project author
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        temp_author = project.authors.create(
            user=editor2,
            display_order=project.authors.count() + 1,
        )
        temp_author.affiliations.create(name='MIT')

        # Submit project
        self.assertTrue(project.is_submittable())
        project.submit(author_comments='')
        self.assertIsNone(project.editor)
        self.assertEqual(project.submission_status, SubmissionStatus.NEEDS_ASSIGNMENT)

        # Assign editor1 as initial editor
        self.client.login(username='admin', password='Tester11!')
        self.client.post(reverse('submitted_projects'), data={
            'assign_editor': '',
            'project': project.id,
            'editor': editor1.id,
        })
        project.refresh_from_db()
        self.assertEqual(project.editor, editor1)
        self.assertEqual(project.submission_status, SubmissionStatus.NEEDS_DECISION)

        # Try to reassign to editor2; this should fail
        self.client.login(username=editor1.username, password='Tester11!')
        self.client.post(
            reverse('submission_info', args=(project.slug,)),
            data={
                'reassign_editor': '',
                'editor': editor2.id,
            },
        )
        project.refresh_from_db()
        self.assertEqual(project.editor, editor1)

        # Remove author and try to reassign again
        temp_author.delete()
        self.client.login(username=editor1.username, password='Tester11!')
        self.client.post(
            reverse('submission_info', args=(project.slug,)),
            data={
                'reassign_editor': '',
                'editor': editor2.id,
            },
        )
        project.refresh_from_db()
        self.assertEqual(project.editor, editor2)

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
            'reopen_copyedit', args=(project.slug,)),
            data={'reopen_copyedit':''})
        project = ActiveProject.objects.get(id=project.id)
        self.assertTrue(project.copyeditable())

        # Erase a required field
        project.refresh_from_db()
        project.abstract = ''
        project.save()

        # "Complete copyedit" should fail because abstract is missing
        response = self.client.post(
            reverse('copyedit_submission', args=(project.slug,)), data={
                'complete_copyedit': '',
                'made_changes': 1,
                'changelog_summary': 'Removed abstract',
            })
        project.refresh_from_db()
        self.assertTrue(project.copyeditable())

        # Restore abstract
        project.refresh_from_db()
        project.abstract = '<p>Database of annotated ECGs</p>'
        project.save()

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

        # Reopen copyedit
        self.client.login(username='admin', password='Tester11!')
        self.client.post(reverse(
            'reopen_copyedit', args=(project.slug,)
        ), data={
            'reopen_copyedit': '',
        })
        project.refresh_from_db()
        self.assertTrue(project.copyeditable())
        self.assertFalse(project.is_publishable())

        # Complete copyedit again
        self.client.post(reverse(
            'copyedit_submission', args=(project.slug,)
        ), data={
            'complete_copyedit': '',
            'made_changes': 1,
            'changelog_summary': 'blah blah',
        })
        project.refresh_from_db()
        self.assertFalse(project.copyeditable())
        self.assertFalse(project.is_publishable())

        # Approve again
        self.client.login(username='rgmark', password='Tester11!')
        self.client.post(reverse(
            'project_submission', args=(project.slug,)
        ), data={
            'approve_publication': '',
        })
        project.refresh_from_db()
        self.assertTrue(project.is_publishable())


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
                data={'slug': taken_slug, 'doi': False, 'make_zip': 1, 'georestricted': False})
            self.assertTrue(bool(ActiveProject.objects.filter(
                slug=project_slug)))

        # Publish with a valid custom slug
        response = self.client.post(reverse(
            'publish_submission', args=(project.slug,)),
            data={'slug': custom_slug, 'doi': False, 'make_zip': 1, 'georestricted': False})

        # Run background tasks
        self.assertBackgroundTasks(1)

        self.assertTrue(bool(PublishedProject.objects.filter(slug=custom_slug)))
        self.assertFalse(bool(PublishedProject.objects.filter(slug=project_slug)))
        self.assertFalse(bool(ActiveProject.objects.filter(slug=project_slug)))

        project = PublishedProject.objects.get(slug=custom_slug,
                                               version=project.version)
        self.assertEqual(project.submission_slug, project_slug)
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


class TestPublished(TestCase):
    """
    Test functions for managing published projects.
    """

    @requests_mock.Mocker()
    def test_register_doi(self, mocker):
        """
        Test registering new DOIs for a published project.
        """
        self.client.login(username='admin', password='Tester11!')

        project = PublishedProject.objects.get(slug='demowave',
                                               version='1.0.0')
        self.assertIsNone(project.doi)
        self.assertIsNone(project.core_project.doi)
        self.assertTrue(project.is_latest_version)

        site = Site.objects.get_current()
        site_url = 'https://' + site.domain
        published_url = site_url + reverse('published_project',
                                           args=(project.slug,
                                                 project.version))
        core_url = site_url + reverse('published_project_latest',
                                      args=(project.slug,))

        management_url = reverse('manage_published_project',
                                 args=(project.slug, project.version))

        with self.settings(
                DATACITE_API_URL='https://api.datacite.example/dois',
                DATACITE_USER='admin',
                DATACITE_PASSWORD='letmein',
                DATACITE_PREFIX='10.0000'):

            # Create new versioned DOI
            mocker.post('https://api.datacite.example/dois', [
                {'text': json.dumps(
                    {'data': {'attributes': {'doi': '10.0000/ccc'}}})},
            ])
            response = self.client.post(management_url, data={
                'create_doi_version': ''
            })
            self.assertEqual(response.status_code, 200)

            project.refresh_from_db()
            self.assertEqual(project.doi, '10.0000/ccc')

            payload = mocker.last_request.json()
            self.assertEqual(payload['data']['type'], 'dois')

            attributes = payload['data']['attributes']
            self.assertEqual(attributes['event'], 'publish')
            self.assertEqual(attributes['publicationYear'],
                             project.publish_datetime.year)
            self.assertEqual(attributes['url'], published_url)

            # Create new core DOI
            mocker.post('https://api.datacite.example/dois', [
                {'text': json.dumps(
                    {'data': {'attributes': {'doi': '10.0000/ddd'}}})},
            ])
            response = self.client.post(management_url, data={
                'create_doi_core': ''
            })
            self.assertEqual(response.status_code, 200)

            project.core_project.refresh_from_db()
            self.assertEqual(project.core_project.doi, '10.0000/ddd')

            payload = mocker.last_request.json()
            self.assertEqual(payload['data']['type'], 'dois')

            attributes = payload['data']['attributes']
            self.assertEqual(attributes['event'], 'publish')
            self.assertEqual(attributes['publicationYear'],
                             project.publish_datetime.year)
            self.assertEqual(attributes['url'], core_url)

    @requests_mock.Mocker()
    def test_update_doi(self, mocker):
        """
        Test updating existing DOIs for a published project.
        """
        self.client.login(username='admin', password='Tester11!')

        project = PublishedProject.objects.get(slug='demopsn',
                                               version='1.0')
        self.assertIsNotNone(project.doi)
        self.assertIsNotNone(project.core_project.doi)
        self.assertTrue(project.is_latest_version)

        doi = project.doi
        core_doi = project.core_project.doi

        site = Site.objects.get_current()
        site_url = 'https://' + site.domain
        published_url = site_url + reverse('published_project',
                                           args=(project.slug,
                                                 project.version))
        core_url = site_url + reverse('published_project_latest',
                                      args=(project.slug,))

        management_url = reverse('manage_published_project',
                                 args=(project.slug, project.version))

        with self.settings(
                DATACITE_API_URL='https://api.datacite.example/dois',
                DATACITE_USER='admin',
                DATACITE_PASSWORD='letmein',
                DATACITE_PREFIX='10.0000'):

            # Update versioned DOI
            mocker.put('https://api.datacite.example/dois/' + doi)
            response = self.client.post(management_url, data={
                'update_doi_version': ''
            })
            self.assertEqual(response.status_code, 200)

            project.refresh_from_db()
            self.assertEqual(project.doi, doi)

            payload = mocker.last_request.json()
            self.assertEqual(payload['data']['type'], 'dois')

            attributes = payload['data']['attributes']
            self.assertEqual(attributes['event'], 'publish')
            self.assertEqual(attributes['publicationYear'],
                             project.publish_datetime.year)
            self.assertEqual(attributes['url'], published_url)

            # Update core DOI
            mocker.put('https://api.datacite.example/dois/' + core_doi)
            response = self.client.post(management_url, data={
                'update_doi_core': ''
            })
            self.assertEqual(response.status_code, 200)

            project.core_project.refresh_from_db()
            self.assertEqual(project.core_project.doi, core_doi)

            payload = mocker.last_request.json()
            self.assertEqual(payload['data']['type'], 'dois')

            attributes = payload['data']['attributes']
            self.assertEqual(attributes['event'], 'publish')
            self.assertEqual(attributes['publicationYear'],
                             project.publish_datetime.year)
            self.assertEqual(attributes['url'], core_url)


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


class TestAnonymousAccess(TestMixin):
    """
    Test anonymous access functionality for project previews,
    including standard and author-masked links.
    """

    def setUp(self):
        super().setUp()
        self.project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.editor = User.objects.get(username='admin')
        self.client.login(username='admin', password='Tester11!')

    def test_generate_standard_anonymous_link(self):
        """
        Test generating a standard anonymous access link (shows authors)
        """
        # Ensure no anonymous access exists initially
        self.assertEqual(self.project.anonymous.count(), 0)

        # Generate standard anonymous link
        self.client.post(
            reverse('submission_info', args=[self.project.slug]),
            data={'generate_passphrase': ''}
        )

        # Check that anonymous access was created
        self.assertEqual(self.project.anonymous.count(), 1)
        anonymous = self.project.anonymous.first()
        self.assertIsNotNone(anonymous)
        self.assertFalse(anonymous.hide_authors)
        self.assertIsNotNone(anonymous.url)
        self.assertIsNotNone(anonymous.passphrase)

    def test_generate_author_masked_anonymous_link(self):
        """
        Test generating an author-masked anonymous access link (hides authors)
        """
        # Ensure no anonymous access exists initially
        self.assertEqual(self.project.anonymous.count(), 0)

        # Generate author-masked anonymous link
        self.client.post(
            reverse('submission_info', args=[self.project.slug]),
            data={'generate_passphrase_masked': ''}
        )

        # Check that anonymous access was created with hide_authors=True
        self.assertEqual(self.project.anonymous.count(), 1)
        anonymous = self.project.anonymous.first()
        self.assertIsNotNone(anonymous)
        self.assertTrue(anonymous.hide_authors)
        self.assertIsNotNone(anonymous.url)
        self.assertIsNotNone(anonymous.passphrase)

    def test_regenerate_link_changes_hide_authors_flag(self):
        """
        Test that regenerating a link can change the hide_authors flag
        """
        # Generate standard link first
        self.client.post(
            reverse('submission_info', args=[self.project.slug]),
            data={'generate_passphrase': ''}
        )
        anonymous = self.project.anonymous.first()
        self.assertFalse(anonymous.hide_authors)

        # Regenerate as author-masked link
        self.client.post(
            reverse('submission_info', args=[self.project.slug]),
            data={'generate_passphrase_masked': ''}
        )
        anonymous.refresh_from_db()
        self.assertTrue(anonymous.hide_authors)

        # Regenerate as standard link again
        self.client.post(
            reverse('submission_info', args=[self.project.slug]),
            data={'generate_passphrase': ''}
        )
        anonymous.refresh_from_db()
        self.assertFalse(anonymous.hide_authors)

    def test_remove_anonymous_access(self):
        """
        Test revoking anonymous access
        """
        # Generate anonymous link
        self.client.post(
            reverse('submission_info', args=[self.project.slug]),
            data={'generate_passphrase': ''}
        )
        self.assertEqual(self.project.anonymous.count(), 1)

        # Revoke access
        self.client.post(
            reverse('submission_info', args=[self.project.slug]),
            data={'remove_passphrase': ''}
        )

        # Check that anonymous access was deleted
        self.assertEqual(self.project.anonymous.count(), 0)

    def test_author_masked_preview_hides_author_info(self):
        """
        Test that author information is hidden in preview when using author-masked link
        """
        # Generate author-masked link
        url, passphrase = self.project.generate_anonymous_access(hide_authors=True)

        # Login using the anonymous access credentials
        self.client.post(
            reverse('anonymous_login', args=[url]),
            data={'passphrase': passphrase}
        )

        # Access the preview page
        response = self.client.get(reverse('project_preview', args=[self.project.slug]))

        # Check that the response contains the "hidden for blind review" text
        self.assertContains(response, 'Author information hidden')

        # Check that author names are NOT in the response
        authors = self.project.authors.all()
        for author in authors:
            self.assertNotContains(response, author.get_full_name())

    def test_standard_preview_shows_author_info(self):
        """
        Test that author information is shown in preview when using standard link
        """
        # Generate standard link
        url, passphrase = self.project.generate_anonymous_access(hide_authors=False)

        # Login using the anonymous access credentials
        self.client.post(
            reverse('anonymous_login', args=[url]),
            data={'passphrase': passphrase}
        )

        # Access the preview page
        response = self.client.get(reverse('project_preview', args=[self.project.slug]))

        # Check that the response does NOT contain the "hidden" text
        self.assertNotContains(response, 'Author information hidden')

        # Check that author names ARE in the response
        authors = self.project.authors.all()
        for author in authors:
            self.assertContains(response, author.get_full_name())


class TestOnHold(TestMixin):
    """
    Test the on-hold functionality for active projects.
    """

    PROJECT_TITLE = 'MIT-BIH Arrhythmia Database'
    ADMIN_USER = 'admin'
    ADMIN_PASSWORD = 'Tester11!'
    EDITOR_USER = 'amitupreti'
    EDITOR_PASSWORD = 'Tester11!'
    NON_EDITOR_USER = 'cindyehlert'
    NON_EDITOR_PASSWORD = 'Tester11!'

    def _submit_and_assign(self, editor_username=None):
        """Submit the project and optionally assign an editor."""
        project = ActiveProject.objects.get(title=self.PROJECT_TITLE)
        project.submit(author_comments='')
        if editor_username:
            editor = User.objects.get(username=editor_username)
            self.client.login(username=self.ADMIN_USER, password=self.ADMIN_PASSWORD)
            self.client.post(reverse('submitted_projects'), data={
                'assign_editor': '',
                'project': project.id,
                'editor': editor.id,
            })
            project.refresh_from_db()
        return project

    def test_place_on_hold_as_admin(self):
        """Admin can place an unassigned project on hold."""
        project = self._submit_and_assign()
        self.client.login(username=self.ADMIN_USER, password=self.ADMIN_PASSWORD)
        self.client.post(reverse('project_on_hold', args=(project.slug,)), data={
            'place_on_hold': '',
        })
        project.refresh_from_db()
        self.assertTrue(project.is_on_hold)

    def test_place_on_hold_as_editor(self):
        """The assigned editor can place their project on hold."""
        project = self._submit_and_assign(self.EDITOR_USER)
        self.client.login(username=self.EDITOR_USER, password=self.EDITOR_PASSWORD)
        self.client.post(reverse('project_on_hold', args=(project.slug,)), data={
            'place_on_hold': '',
        })
        project.refresh_from_db()
        self.assertTrue(project.is_on_hold)

    def test_place_on_hold_denied_for_non_editor(self):
        """An editor who is not assigned to the project cannot place it on hold."""
        project = self._submit_and_assign(self.EDITOR_USER)
        self.client.login(username=self.NON_EDITOR_USER, password=self.NON_EDITOR_PASSWORD)
        self.client.post(reverse('project_on_hold', args=(project.slug,)), data={
            'place_on_hold': '',
        })
        project.refresh_from_db()
        self.assertFalse(project.is_on_hold)

    def test_remove_from_hold(self):
        """A project can be taken off hold."""
        project = self._submit_and_assign(self.EDITOR_USER)
        project.place_on_hold()
        self.assertTrue(project.is_on_hold)

        self.client.login(username=self.EDITOR_USER, password=self.EDITOR_PASSWORD)
        self.client.post(reverse('project_on_hold', args=(project.slug,)), data={
            'remove_from_hold': '',
        })
        project.refresh_from_db()
        self.assertFalse(project.is_on_hold)

    def test_on_hold_preserves_submission_status(self):
        """Placing on hold does not change the submission status."""
        project = self._submit_and_assign(self.EDITOR_USER)
        original_status = project.submission_status
        project.place_on_hold()
        project.refresh_from_db()
        self.assertEqual(project.submission_status, original_status)
        self.assertTrue(project.is_on_hold)

    def test_on_hold_project_hidden_from_active_tabs(self):
        """On-hold projects should not appear in the active tab listings."""
        project = self._submit_and_assign(self.EDITOR_USER)
        project.place_on_hold()

        self.client.login(username=self.ADMIN_USER, password=self.ADMIN_PASSWORD)
        response = self.client.get(reverse('submitted_projects'))
        self.assertNotIn(project, response.context['decision_projects'])
        self.assertIn(project, response.context['on_hold_projects'])

    def test_removed_from_hold_project_returns_to_active_tab(self):
        """A project removed from hold should reappear in its active tab."""
        project = self._submit_and_assign(self.EDITOR_USER)
        project.place_on_hold()
        project.remove_from_hold()

        self.client.login(username=self.ADMIN_USER, password=self.ADMIN_PASSWORD)
        response = self.client.get(reverse('submitted_projects'))
        self.assertIn(project, response.context['decision_projects'])
        self.assertNotIn(project, response.context['on_hold_projects'])

    def test_on_hold_shown_on_submission_info(self):
        """The submission info page should show the on-hold badge."""
        project = self._submit_and_assign(self.EDITOR_USER)
        project.place_on_hold()

        self.client.login(username=self.ADMIN_USER, password=self.ADMIN_PASSWORD)
        response = self.client.get(reverse('submission_info', args=(project.slug,)))
        self.assertContains(response, 'On Hold')

    def test_editor_home_excludes_on_hold(self):
        """On-hold projects should be excluded from the editor home active lists."""
        project = self._submit_and_assign(self.EDITOR_USER)
        project.place_on_hold()

        self.client.login(username=self.EDITOR_USER, password=self.EDITOR_PASSWORD)
        response = self.client.get(reverse('editor_home'))
        self.assertNotIn(project, response.context['decision_projects'])
        self.assertIn(project, response.context['on_hold_projects'])
