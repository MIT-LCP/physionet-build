
import base64
import os
from http import HTTPStatus
import json
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from project.forms import ContentForm
from project.models import (
    AccessPolicy,
    ActiveProject,
    Author,
    AuthorInvitation,
    DataAccessRequest,
    DataAccessRequestReviewer,
    License,
    PublishedAuthor,
    PublishedProject,
    StorageRequest,
    SubmissionStatus
)
from user.models import User
from user.test_views import TestMixin, prevent_request_warnings

PROJECT_VIEWS = [
    'project_overview', 'project_authors', 'project_content',
    'project_access', 'project_discovery', 'project_files',
    'project_proofread', 'project_preview', 'project_submission'
]

def _basic_auth(username, password, encoding='UTF-8'):
    """
    Generate an HTTP Basic authorization header.
    """
    token = username + ':' + password
    token = base64.b64encode(token.encode(encoding)).decode()
    return 'Basic ' + token


class TestAccessPresubmission(TestMixin):
    """
    Test that certain views or content in their various states can only
    be accessed by the appropriate users.

    Projects in presubmission state.

    """

    @prevent_request_warnings
    def test_visit_get(self):
        """
        Test visiting all project pages.

        """
        project = ActiveProject.objects.get(title='MIMIC-III Clinical Database')

        # Visit all the views of the project, along with a file download
        # as submitting author
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('serve_active_project_file',
            args=(project.slug, 'notes/notes.txt')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('display_active_project_file',
            args=(project.slug, 'notes')))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse('display_active_project_file',
            args=(project.slug, 'notes/notes.txt')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('display_active_project_file',
            args=(project.slug, 'notes/notes.txt/fnord')))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('display_active_project_file',
            args=(project.slug, 'fnord')))
        self.assertEqual(response.status_code, 404)

        # Visit as project coauthor
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('serve_active_project_file',
            args=(project.slug, 'notes/notes.txt')))
        self.assertEqual(response.status_code, 200)

        # Visit as non-author
        self.client.login(username='george@mit.edu', password='Tester11!')
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse('serve_active_project_file',
            args=(project.slug, 'notes/notes.txt')))
        self.assertEqual(response.status_code, 403)

        # Visit non-existent project
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=('fnord',)))
            self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse('serve_active_project_file',
            args=('fnord', 'notes/notes.txt')))
        self.assertEqual(response.status_code, 403)

    @prevent_request_warnings
    def test_project_authors(self):
        """
        Test project_authors post.

        """
        project = ActiveProject.objects.get(title='MIMIC-III Clinical Database')

        # Non-submitting author
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        # Not allowed to invite authors
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'invite_author':'', 'email':'admin@mit.edu'})
        self.assertFalse(AuthorInvitation.objects.filter(email='admin@mit.edu', project=project))
        # Change corresponding email as corresponding author.
        # Valid and invalid emails.
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'corresponding_email':'', 'associated_email':'aewj@mit.edu'})
        self.assertMessage(response, 25)
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'corresponding_email':'', 'associated_email':'rgmark@mit.edu'})
        self.assertMessage(response, 40)

        # Submitting author
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        # Invite author
        # Outstanding invitation
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'invite_author':'', 'email':'george@mit.edu'})
        self.assertMessage(response, 40)
        # Already an author
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'invite_author':'', 'email':'rgmark@mit.edu'})
        self.assertMessage(response, 40)
        # Non-author
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'invite_author':'', 'email':'admin@mit.edu'})
        self.assertMessage(response, 25)

        # Change corresponding email, but user is not corresponding author.
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'corresponding_email':'', 'associated_email':'rgmark@gmail.com'})
        self.assertEqual(project.authors.get(
            user=response.context['user']).corresponding_email.email,
            'rgmark@mit.edu')

        # Select corresponding author
        # Not a valid author
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'corresponding_author':'', 'author':999999})
        self.assertMessage(response, 40)
        # Valid author
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'corresponding_author':'', 'author':4})
        self.assertMessage(response, 25)
        self.assertEqual(project.corresponding_author().user.username, 'aewj')

    @prevent_request_warnings
    def test_project_access(self):
        """
        Post requests for project_access.
        """
        project = ActiveProject.objects.get(title='MIMIC-III Clinical Database')

        # Submitting author
        self.client.login(username='rgmark@mit.edu', password='Tester11!')

        # Ensure valid license policy combination
        open_data_license = License.objects.filter(
            access_policy=AccessPolicy.OPEN, project_types__pk=0
        ).first()
        restricted_data_license = License.objects.filter(
            access_policy=AccessPolicy.RESTRICTED, project_types__pk=0
        ).first()
        software_license = License.objects.filter(project_types__pk=1).first()

        response = self.client.post(
            reverse('project_access', args=(project.slug,)),
            data={'access_policy': AccessPolicy.OPEN.value, 'license': open_data_license.id},
        )
        self.assertMessage(response, 25)

        response = self.client.post(
            reverse('project_access', args=(project.slug,)),
            data={'access_policy': AccessPolicy.OPEN.value, 'license': restricted_data_license.id},
        )
        self.assertMessage(response, 40)

        response = self.client.post(
            reverse('project_access', args=(project.slug,)),
            data={'access_policy': AccessPolicy.OPEN.value, 'license': software_license.id},
        )
        self.assertMessage(response, 40)

        # Non-submitting author is not allowed
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        response = self.client.post(
            reverse('project_access', args=(project.slug,)),
            data={'access_policy': AccessPolicy.OPEN.value, 'license': open_data_license.id},
        )
        self.assertEqual(response.status_code, 403)

    @prevent_request_warnings
    def test_project_files(self):
        """
        Post requests for project_files.

        """
        project = ActiveProject.objects.get(title='MIMIC-III Clinical Database')
        # Submitting author
        self.client.login(username='rgmark@mit.edu', password='Tester11!')

        # Create folder
        # Clashing item name
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'create_folder':'', 'folder_name':'D_ITEMS.csv.gz'})
        self.assertMessage(response, 40)
        # Valid new folder
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'create_folder':'', 'folder_name':'new-patients'})
        self.assertMessage(response, 25)
        # Invalid subdir (contains ..)
        response = self.client.post(
            reverse('project_files', args=(project.slug,)),
            data={'create_folder': '', 'subdir': 'new-patients/..',
                  'folder_name': 'blabla'})
        self.assertMessage(response, 40)
        # Invalid subdir (absolute path)
        response = self.client.post(
            reverse('project_files', args=(project.slug,)),
            data={'create_folder': '', 'subdir': project.file_root(),
                  'folder_name': 'blabla2'})
        self.assertMessage(response, 40)

        # Rename Item
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'rename_item':'', 'subdir':'', 'items':'new-patients',
                  'new_name':'updated-patients'})
        self.assertMessage(response, 25)
        self.assertTrue(os.path.isdir(os.path.join(project.file_root(), 'updated-patients')))

        # Move Items
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'move_items':'', 'subdir':'', 'items':['ICUSTAYS.csv.gz', 'PATIENTS.csv.gz'],
                  'destination_folder':'notes'})
        self.assertMessage(response, 25)
        self.assertTrue(os.path.isfile(os.path.join(project.file_root(), 'notes', 'ICUSTAYS.csv.gz')))
        self.assertTrue(os.path.isfile(os.path.join(project.file_root(), 'notes', 'PATIENTS.csv.gz')))

        # Delete Items
        # Invalid items
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'delete_items':'', 'subdir':'', 'items':['ICUSTAYS.csv.gz', 'PATIENTS.csv.gz']})
        self.assertMessage(response, 40)
        self.assertTrue(os.path.isfile(os.path.join(project.file_root(), 'notes', 'ICUSTAYS.csv.gz')))
        # Invalid subdir
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'delete_items': '', 'subdir': os.path.join(project.file_root(), 'notes'),
                  'items': ['ICUSTAYS.csv.gz', 'PATIENTS.csv.gz']})
        self.assertMessage(response, 40)
        self.assertTrue(os.path.isfile(os.path.join(project.file_root(), 'notes', 'ICUSTAYS.csv.gz')))
        self.assertTrue(os.path.isfile(os.path.join(project.file_root(), 'notes', 'PATIENTS.csv.gz')))
        # Existing items
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'delete_items':'', 'subdir':'notes', 'items':['ICUSTAYS.csv.gz', 'PATIENTS.csv.gz']})
        self.assertMessage(response, 25)
        self.assertFalse(os.path.isfile(os.path.join(project.file_root(), 'notes', 'ICUSTAYS.csv.gz')))
        self.assertFalse(os.path.isfile(os.path.join(project.file_root(), 'notes', 'PATIENTS.csv.gz')))

        # Upload file. Use same file content already existing.
        project.refresh_from_db()
        timestamp = project.modified_datetime
        with open(os.path.join(project.file_root(), 'D_ITEMS.csv.gz'), 'rb') as f:
            response = self.client.post(reverse(
                'project_files', args=(project.slug,)),
                data={'upload_files':'', 'subdir':'notes',
                      'file_field':SimpleUploadedFile(f.name, f.read())})
        self.assertMessage(response, 25)

        with open(os.path.join(project.file_root(), 'D_ITEMS.csv.gz'), 'rb') as f:
            f1 = f.read()
        with open(os.path.join(project.file_root(), 'notes', 'D_ITEMS.csv.gz'), 'rb') as f:
            f2 = f.read()
        self.assertEqual(f1, f2)

        project.refresh_from_db()
        self.assertGreater(project.modified_datetime, timestamp)

        # Invalid subdir
        response = self.client.post(
            reverse('project_files', args=(project.slug,)),
            data={'upload_files': '', 'subdir': project.file_root(),
                  'file_field': SimpleUploadedFile('blabla3', b'')})
        self.assertMessage(response, 40)
        self.assertFalse(os.path.isfile(os.path.join(project.file_root(), 'blabla3')))

        # Non-submitting author cannot post
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'create_folder':'', 'folder_name':'new-folder-valid'})
        self.assertEqual(response.status_code, 403)

    def test_project_file_upload(self):
        """
        Additional test cases for project_files.
        """
        project = ActiveProject.objects.get(title='MIMIC-III Clinical Database')
        self.client.login(username='rgmark@mit.edu', password='Tester11!')

        # Set a small storage allowance
        project.core_project.storage_allowance = project.storage_used() + 50000
        project.core_project.save()

        # Upload multiple files
        self.client.post(reverse('project_files', args=(project.slug,)), data={
            'upload_files': '', 'subdir': '',
            'file_field': (
                SimpleUploadedFile('t1', b'x'),
                SimpleUploadedFile('t2', b'x'),
            )
        })
        self.assertTrue(os.path.exists(os.path.join(project.file_root(), 't1')))
        self.assertTrue(os.path.exists(os.path.join(project.file_root(), 't2')))

        # Upload a file with an invalid name
        self.client.post(reverse('project_files', args=(project.slug,)), data={
            'upload_files': '', 'subdir': '',
            'file_field': (
                SimpleUploadedFile('\n', b'x'),
            )
        })
        self.assertFalse(os.path.exists(os.path.join(project.file_root(), '\n')))

        # Upload files whose combined size exceeds allowance
        self.client.post(reverse('project_files', args=(project.slug,)), data={
            'upload_files': '', 'subdir': '',
            'file_field': (
                SimpleUploadedFile('t3', b'x' * 30000),
                SimpleUploadedFile('t4', b'x' * 30000),
            )
        })
        self.assertFalse(os.path.exists(os.path.join(project.file_root(), 't3')))
        self.assertFalse(os.path.exists(os.path.join(project.file_root(), 't4')))


class TestProjectCreation(TestMixin):
    """
    Test that we can create new projects and new versions.
    """

    def test_new_project(self):
        """
        Test that we can create a new project from scratch.
        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')

        # Create project
        response = self.client.post(
            reverse('create_project'),
            data={
                'resource_type': 0,
                'title': 'Neuro-Electric Widget Database',
                'abstract': '<p>Test</p>',
            })
        self.assertEqual(response.status_code, 302)
        project = ActiveProject.objects.get(
            title='Neuro-Electric Widget Database')
        self.assertEqual(response['Location'],
                         reverse('project_overview', args=(project.slug,)))

        # Load overview page
        response = self.client.get(
            reverse('project_overview', args=(project.slug,)))
        self.assertEqual(response.status_code, 200)

        # Upload a file
        response = self.client.post(
            reverse('project_files', args=(project.slug,)),
            data={
                'upload_files': '',
                'subdir': '',
                'file_field': SimpleUploadedFile('asdf', b'hello world'),
            })
        self.assertEqual(response.status_code, 200)
        with open(os.path.join(project.file_root(), 'asdf')) as f:
            self.assertEqual(f.read(), 'hello world')

    def test_new_version(self):
        """
        Test that we can create a new version of a published project.
        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')

        oldproject = PublishedProject.objects.get(
            title='Demo eICU Collaborative Research Database')
        response = self.client.post(
            reverse('new_project_version', args=(oldproject.slug,)),
            data={
                'version': '3.0.0',
            })
        self.assertEqual(response.status_code, 302)
        newproject = ActiveProject.objects.get(
            title='Demo eICU Collaborative Research Database')
        self.assertEqual(response['Location'],
                         reverse('project_overview', args=(newproject.slug,)))

        # Check that attributes are copied correctly
        self.assertEqual(newproject.abstract, oldproject.abstract)
        self.assertEqual(newproject.core_project, oldproject.core_project)
        self.assertEqual(newproject.access_policy, oldproject.access_policy)
        self.assertEqual(newproject.version, '3.0.0')

        # Load overview page
        response = self.client.get(
            reverse('project_overview', args=(newproject.slug,)))
        self.assertEqual(response.status_code, 200)

        # Existing files should be hard-linked
        oldpath = os.path.join(oldproject.file_root(), 'admissions.csv')
        newpath = os.path.join(newproject.file_root(), 'admissions.csv')
        self.assertTrue(os.path.samefile(oldpath, newpath))

        # SHA256SUMS.txt should not be linked
        oldpath = os.path.join(oldproject.file_root(), 'SHA256SUMS.txt')
        newpath = os.path.join(newproject.file_root(), 'SHA256SUMS.txt')
        self.assertTrue(os.path.exists(oldpath))
        self.assertFalse(os.path.exists(newpath))

        # Test quota functions: published files should not be counted
        # by active project quota - so deleting a file shouldn't
        # affect inodes_used
        quota = newproject.quota_manager()
        num_inodes = quota.inodes_used
        newpath = os.path.join(newproject.file_root(), 'admissions.csv')
        os.unlink(newpath)
        quota.refresh()
        self.assertEqual(quota.inodes_used, num_inodes)

        # Uploading a new file should be counted by active project quota
        num_inodes = quota.inodes_used
        num_bytes = quota.bytes_used
        with open(newpath, 'w') as f:
            f.write('hello world')
        quota.refresh()
        self.assertEqual(quota.inodes_used, num_inodes + 1)
        self.assertGreater(quota.bytes_used, num_bytes)


class TestProjectEditing(TestCase):
    """
    Tests for the submitting author to edit the project information.
    """

    AUTHOR = 'rgmark@mit.edu'
    PASSWORD = 'Tester11!'
    PROJECT_TITLE = 'MIT-BIH Arrhythmia Database'

    def test_content(self):
        """
        Test editing the project page content.
        """
        self.client.login(username=self.AUTHOR, password=self.PASSWORD)

        project = ActiveProject.objects.get(title=self.PROJECT_TITLE)
        self.assertTrue(project.is_submittable())

        content_url = reverse('project_content', args=(project.slug,))
        response = self.client.get(content_url)
        self.assertEqual(response.status_code, 200)

        # Test post with existing data
        # (abstract, background, content_description, etc.)
        data = {
            'project-reference-content_type-object_id-TOTAL_FORMS': '0',
            'project-reference-content_type-object_id-INITIAL_FORMS': '0',
            'project-reference-content_type-object_id-MIN_NUM_FORMS': '0',
            'project-reference-content_type-object_id-MAX_NUM_FORMS': '0',
        }
        for field in ContentForm.FIELDS[project.resource_type.id]:
            data[field] = getattr(project, field)

        response = self.client.post(content_url, data=data)
        self.assertEqual(response.status_code, 200)

        project.refresh_from_db()
        timestamp = project.modified_datetime

        # Post some HTML, and verify that forbidden tags/attributes
        # are removed
        input_html = """
        <p>
        Example text with <em>emphasis</em>, <code>sample code</code>,
        <a href="https://physionet.org">links</a>,
        <math><mi>&#960;</mi><mo>=</mo>
        <mfrac><mn>22</mn><mn>7</mn></mfrac></math>,
        some ambiguous characters & < >,
        <form>invalid tags</form>,
        <span onclick="evil()">invalid attributes</span>
        </p>
        """

        expected_html = """
        <p>
        Example text with <em>emphasis</em>, <code>sample code</code>,
        <a href="https://physionet.org">links</a>,
        <math><mi>&#960;</mi><mo>=</mo>
        <mfrac><mn>22</mn><mn>7</mn></mfrac></math>,
        some ambiguous characters &amp; &lt; &gt;,
        &lt;form&gt;invalid tags&lt;/form&gt;,
        <span>invalid attributes</span>
        </p>
        """

        data['background'] = input_html
        response = self.client.post(content_url, data=data)
        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertHTMLEqual(project.background, expected_html)
        self.assertGreater(project.modified_datetime, timestamp)

        # Post some blank text in a required field and verify that the
        # project cannot be submitted
        self.assertTrue(project.is_submittable())
        data['background'] = '<p>&nbsp;</p>'
        response = self.client.post(content_url, data=data)
        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertFalse(project.is_submittable())


class TestProjectTransfer(TestCase):
    """
    Tests that submitting author status can be transferred to a co-author
    """
    AUTHOR_EMAIL = 'rgmark@mit.edu'
    COAUTHOR_EMAIL = 'aewj@mit.edu'
    PASSWORD = 'Tester11!'
    PROJECT_SLUG = 'T108xFtYkRAxiRiuOLEJ'

    def setUp(self):
        self.client.login(username=self.AUTHOR_EMAIL, password=self.PASSWORD)
        self.project = ActiveProject.objects.get(slug=self.PROJECT_SLUG)
        self.submitting_author = self.project.authors.filter(is_submitting=True).first()
        self.coauthor = self.project.authors.filter(is_submitting=False).first()

    def test_transfer_author(self):
        """
        Test that an activate project can be transferred to a co-author.
        """
        self.assertEqual(self.submitting_author.user.email, self.AUTHOR_EMAIL)
        self.assertEqual(self.coauthor.user.email, self.COAUTHOR_EMAIL)

        response = self.client.post(
            reverse('project_authors', args=(self.project.slug,)),
            data={
                'transfer_author': self.coauthor.user.id,
            })

        # Check if redirect happens, implying successful transfer
        self.assertEqual(response.status_code, 302)

        # Fetch the updated project data
        updated_project = ActiveProject.objects.get(slug=self.PROJECT_SLUG)

        # Verify that the author has been transferred
        self.assertFalse(updated_project.authors.get(user=self.submitting_author.user).is_submitting)
        self.assertTrue(updated_project.authors.get(user=self.coauthor.user).is_submitting)


class TestAccessPublished(TestMixin):
    """
    Test that certain views or content in their various states can only
    be accessed by the appropriate users.

    Published projects.

    """
    @prevent_request_warnings
    def test_credentialed(self):
        """
        Test access to a credentialed project, including dua signing.
        """
        project = PublishedProject.objects.get(title='Demo eICU Collaborative Research Database')

        # Public user. Anyone can access landing page.
        response = self.client.get(reverse('published_project',
            args=(project.slug, project.version)))
        self.assertEqual(response.status_code, 200)
        # Cannot access files
        response = self.client.get(reverse(
            'serve_published_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse(
            'display_published_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse(
            'published_project_subdir',
            args=(project.slug, project.version, 'timeseries')))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse(
            'published_project_subdir',
            args=(project.slug, project.version, 'fnord')))
        self.assertEqual(response.status_code, 403)

        # Non-credentialed user
        self.client.login(username='admin@mit.edu', password='Tester11!')
        response = self.client.get(reverse(
            'serve_published_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse(
            'published_project_subdir',
            args=(project.slug, project.version, 'timeseries')))
        self.assertEqual(response.status_code, 403)

        # Credentialed user that has not signed dua
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        response = self.client.get(reverse(
            'serve_published_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 403)
        response = self.client.get(reverse(
            'published_project_subdir',
            args=(project.slug, project.version, 'timeseries')))
        self.assertEqual(response.status_code, 403)

        # Sign the dua and get file again
        response = self.client.post(reverse('sign_dua',
            args=(project.slug, project.version,)),
            data={'agree':''})
        response = self.client.get(reverse(
            'serve_published_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse(
            'display_published_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse(
            'serve_published_project_file',
            args=(project.slug, project.version, 'admissions.csv')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse(
            'serve_published_project_file',
            args=(project.slug, project.version, 'fnord.txt')))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse(
            'published_project_subdir',
            args=(project.slug, project.version, 'timeseries')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse(
            'published_project_subdir',
            args=(project.slug, project.version, 'fnord')))
        self.assertEqual(response.status_code, 404)

        # Download file using wget
        self.client.logout()
        response = self.client.get(
            reverse('serve_published_project_file',
                    args=(project.slug, project.version, 'SHA256SUMS.txt')),
            secure=True,
            HTTP_USER_AGENT='Wget/1.18')
        self.assertEqual(response.status_code, 401)
        self.client.logout()
        response = self.client.get(
            reverse('serve_published_project_file',
                    args=(project.slug, project.version, 'SHA256SUMS.txt')),
            secure=True,
            HTTP_USER_AGENT='Wget/1.18',
            HTTP_AUTHORIZATION=_basic_auth('admin@mit.edu', 'Tester11!'))
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        response = self.client.get(
            reverse('serve_published_project_file',
                    args=(project.slug, project.version, 'SHA256SUMS.txt')),
            secure=True,
            HTTP_USER_AGENT='libwfdb/10.6.0',
            HTTP_AUTHORIZATION=_basic_auth('rgmark@mit.edu', 'badpassword'))
        self.assertEqual(response.status_code, 401)
        self.client.logout()
        response = self.client.get(
            reverse('serve_published_project_file',
                    args=(project.slug, project.version, 'SHA256SUMS.txt')),
            secure=True,
            HTTP_USER_AGENT='libwfdb/10.6.0',
            HTTP_AUTHORIZATION=_basic_auth('rgmark@mit.edu', 'Tester11!'))
        self.assertEqual(response.status_code, 200)

        # Download archive using wget
        self.client.logout()
        response = self.client.get(
            reverse('serve_published_project_zip',
                    args=(project.slug, project.version)),
            secure=True,
            HTTP_USER_AGENT='Wget/1.18')
        self.assertEqual(response.status_code, 401)
        self.client.logout()
        response = self.client.get(
            reverse('serve_published_project_zip',
                    args=(project.slug, project.version)),
            secure=True,
            HTTP_USER_AGENT='Wget/1.18',
            HTTP_AUTHORIZATION=_basic_auth('rgmark@mit.edu', 'Tester11!'))
        self.assertEqual(response.status_code, 200)

        # Download file using wget on active projects
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')

        self.client.logout()
        response = self.client.get(reverse('serve_active_project_file_editor',
            args=(project.slug, 'RECORDS')), secure=True,
             HTTP_USER_AGENT='Wget/1.18')
        self.assertEqual(response.status_code, 401)

        self.client.logout()
        response = self.client.get(reverse('serve_active_project_file_editor',
            args=(project.slug, 'RECORDS')), secure=True,
            HTTP_USER_AGENT='Wget/1.18',
            HTTP_AUTHORIZATION=_basic_auth('aewj@mit.edu', 'Tester11!'))
        self.assertEqual(response.status_code, 403)

        self.client.logout()
        response = self.client.get(reverse('serve_active_project_file_editor',
            args=(project.slug, 'RECORDS')), secure=True,
            HTTP_USER_AGENT='Wget/1.18',
            HTTP_AUTHORIZATION=_basic_auth('rgmark@mit.edu', 'badpassword'))
        self.assertEqual(response.status_code, 401)

        self.client.logout()
        response = self.client.get(reverse('serve_active_project_file_editor',
            args=(project.slug, 'RECORDS')), secure=True,
            HTTP_USER_AGENT='Wget/1.18',
            HTTP_AUTHORIZATION=_basic_auth('rgmark@mit.edu', 'Tester11!'))
        self.assertEqual(response.status_code, 200)

        self.client.logout()
        response = self.client.get(reverse('serve_active_project_file_editor',
            args=(project.slug, '')), secure=True,
            HTTP_USER_AGENT='Wget/1.18',
            HTTP_AUTHORIZATION=_basic_auth('admin@mit.edu', 'Tester11!'))
        self.assertEqual(response.status_code, 200)

    def test_open(self):
        """
        Test access to an open project.
        """
        project = PublishedProject.objects.get(title='Demo ECG Signal Toolbox')

        # Public user. Anyone can access files and landing page
        response = self.client.get(reverse('published_project',
            args=(project.slug, project.version,)))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('serve_published_project_file',
            args=(project.slug, project.version, 'Makefile')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('display_published_project_file',
            args=(project.slug, project.version, 'Makefile')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('display_published_project_file',
            args=(project.slug, project.version, 'doc')))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse('display_published_project_file',
            args=(project.slug, project.version, 'fnord')))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('display_published_project_file',
            args=(project.slug, project.version, 'Makefile/fnord')))
        self.assertEqual(response.status_code, 404)

        # Raise a 404 if the requested filename is too long
        long_fn = 'Makefile/fnord'*1000
        response = self.client.get(reverse('display_published_project_file',
            args=(project.slug, project.version, long_fn)))
        self.assertEqual(response.status_code, 404)

    @prevent_request_warnings
    def test_nonexistent(self):
        """
        Test access to a non-existent project.
        """
        response = self.client.get(reverse(
            'published_project_latest', args=('fnord',)))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse(
            'published_project', args=('fnord', '1.0')))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse(
            'published_project_subdir', args=('fnord', '1.0', 'data')))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse(
            'serve_published_project_file', args=('fnord', '1.0', 'Makefile')))
        self.assertEqual(response.status_code, 404)

    def test_serve_file(self):
        """
        Test serving files via X-Accel-Redirect.
        """
        with self.settings(MEDIA_X_ACCEL_ALIAS='/protected'):
            # Open project
            project = PublishedProject.objects.get(
                title='Demo ECG Signal Toolbox')

            # Requests for this public URL:
            url = '/files/{}/{}/'.format(project.slug, project.version)
            # should be redirected to this internal path:
            path = '/static/published-projects/{}/{}/'.format(
                project.slug, project.version)

            response = self.client.get(url + 'foo/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Accel-Redirect'], path + 'foo/')
            response = self.client.get(url + 'asdf/%')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Accel-Redirect'], path + 'asdf/%25')
            response = self.client.get(url + '%C3%80')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Accel-Redirect'], path + '%C3%80')

            # Credentialed project
            project = PublishedProject.objects.get(
                title='Demo eICU Collaborative Research Database')

            # Authorized requests for this public URL:
            url = '/files/{}/{}/'.format(project.slug, project.version)
            # should be redirected to this internal path:
            path = '/protected/published-projects/{}/{}/'.format(
                project.slug, project.version)

            response = self.client.get(url + 'foo/')
            self.assertEqual(response.status_code, 403)

            self.client.login(username='rgmark@mit.edu', password='Tester11!')
            response = self.client.post(
                reverse('sign_dua', args=(project.slug, project.version,)),
                data={'agree': ''})

            response = self.client.get(url + 'foo/')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Accel-Redirect'], path + 'foo/')
            response = self.client.get(url + 'asdf/%')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Accel-Redirect'], path + 'asdf/%25')
            response = self.client.get(url + '%C3%80')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Accel-Redirect'], path + '%C3%80')


class TestState(TestMixin):
    """
    Test that all objects are in their intended states, during and
    after review/publication state transitions.

    """
    def test_create_archive(self):
        """
        Create and archive a project
        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        response = self.client.post(reverse('create_project'),
            data={'title': 'Database 1', 'resource_type': 0,
                  'abstract': '<p class=xyz lang=en>x & y'})

        project = ActiveProject.objects.get(title='Database 1')
        self.assertRedirects(response, reverse('project_overview',
            args=(project.slug,)))
        self.assertEqual(project.authors.all().get().user.email, 'rgmark@mit.edu')
        self.assertEqual(project.abstract, '<p lang="en">x &amp; y</p>')

    def test_archive(self):
        """
        Archive a project
        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.assertTrue(ActiveProject.objects.filter(title='MIT-BIH Arrhythmia Database',
                                                     submission_status=SubmissionStatus.UNSUBMITTED))
        author_id = project.authors.all().first().id
        abstract = project.abstract

        # 'Delete' (archive) the project
        response = self.client.post(reverse('project_overview',
            args=(project.slug,)), data={'delete_project':''})

        # The ActiveProject model should be set to "Archived" status
        self.assertFalse(ActiveProject.objects.filter(title='MIT-BIH Arrhythmia Database',
                                                      submission_status=SubmissionStatus.UNSUBMITTED))
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database',
                                            submission_status=SubmissionStatus.ARCHIVED)
        self.assertTrue(Author.objects.get(id=author_id).project == project)
        self.assertEqual(project.abstract, abstract)

    def test_submittable(self):
        """
        Make sure some projects are and others are not able to be
        submitted.
        """
        self.assertTrue(ActiveProject.objects.get(
            title='MIT-BIH Arrhythmia Database').is_submittable())
        self.assertFalse(ActiveProject.objects.get(
            title='MIMIC-III Clinical Database').is_submittable())

    def test_submit(self):
        """
        Submit a ready project
        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.assertFalse(project.under_submission())
        response = self.client.post(reverse(
            'project_submission', args=(project.slug,)),
            data={'submit_project':''})
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        self.assertTrue(project.under_submission())
        self.assertFalse(project.author_editable())


class TestInteraction(TestMixin):
    """
    Test project views that require multiple user interaction that are
    not directly related to reviewing/editing the project.

    """

    def test_storage_request(self):
        """
        Request storage allowance and process the request.
        """
        # Delete existing storage requests to make formset simpler
        StorageRequest.objects.all().delete()

        for decision in range(2):
            self.client.login(username='rgmark@mit.edu', password='Tester11!')
            project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
            response = self.client.post(reverse(
                'project_files', args=(project.slug,)),
                data={'request_storage':'', 'request_allowance':5})
            self.assertMessage(response, 25)

            # Fails with outstanding request
            response = self.client.post(reverse(
                'project_files', args=(project.slug,)),
                data={'request_storage':'', 'request_allowance':5})
            self.assertMessage(response, 40)

            # Process storage request. First time reject, next time accept
            self.client.login(username='admin', password='Tester11!')
            rid = StorageRequest.objects.get(project=project, is_active=True).id
            data = {
                'form-TOTAL_FORMS': ['1'], 'form-MAX_NUM_FORMS': ['1000'],
                'form-0-response': [str(decision)], 'form-MIN_NUM_FORMS': ['0'],
                'form-INITIAL_FORMS': ['1'],
                'form-0-id': [str(rid)], 'storage_response': [str(rid)]
            }
            response = self.client.post(reverse('storage_requests'), data=data)
            self.assertEqual(StorageRequest.objects.get(id=rid).response,
                bool(decision))
        # Test successful allowance increase
        self.assertEqual(ActiveProject.objects.get(
            title='MIT-BIH Arrhythmia Database').storage_allowance(),
            5 * 1024**3)
        # Fails if already has the allowance
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'request_storage':'', 'request_allowance':5})
        self.assertMessage(response, 40)

    def test_invite_author(self):
        """
        Test the functionality of inviting and rejecting/accepting authorship.

        """
        # Test both accept and reject
        for inv_response in range(2):
            # Invite aewj to project as rgmark
            self.client.login(username='rgmark@mit.edu', password='Tester11!')
            project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
            response = self.client.post(reverse(
                'project_authors', args=(project.slug,)),
                data={'invite_author':'', 'email':'aewj@mit.edu'})
            self.assertMessage(response, 25)
            # Try again. Fails with outstanding invitation
            response = self.client.post(reverse(
                'project_authors', args=(project.slug,)),
                data={'invite_author':'', 'email':'aewj@mit.edu'})
            self.assertMessage(response, 40)
            # Process invitation. First time reject, next time accept
            self.client.login(username='aewj', password='Tester11!')
            iid = AuthorInvitation.objects.get(email='aewj@mit.edu',
                project=project, is_active=True).id
            data = {
                'form-TOTAL_FORMS': ['1'], 'form-MAX_NUM_FORMS': ['1000'],
                'form-0-response': [str(inv_response)], 'form-MIN_NUM_FORMS': ['0'],
                'form-0-affiliation': ['MIT' if inv_response else ''],
                'form-INITIAL_FORMS': ['1'],
                'form-0-id': [str(iid)], 'invitation_response': [str(iid)]
            }
            response = self.client.post(reverse('project_home'), data=data)
            self.assertEqual(AuthorInvitation.objects.get(id=iid).response,
                bool(inv_response))

        # Test successful new author
        self.assertTrue(project.authors.filter(user__username='aewj'))
        # Fails if user is already an author
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        response = self.client.post(reverse(
            'project_authors', args=(project.slug,)),
            data={'invite_author':'', 'email':'aewj@mit.edu'})
        self.assertMessage(response, 40)


class TestSelfManagedProjectWorkflows(TestMixin):
    """
    Testing workflows around self-managed projects
    """

    SUBMITTER = 'george'
    REQUESTER = 'rgmark'

    PASSWORD = 'Tester11!'

    PROJECT_NAME = "Self Managed Access Database Demo"

    def test_basic_workflow(self):

        def submit_request(msg_purpose):
            mail_outbox_size = len(mail.outbox)
            self.client.post(reverse('request_data_access',
                                     args=(project.slug, project.version,)),
                             data={
                                 'proj-data_use_purpose': msg_purpose,
                                 'proj-data_use_title': 'example title',
                                 'proj-agree_dua': ['on']})

            da_req = DataAccessRequest.objects.filter(
                requester_id=User.objects.get(username=self.REQUESTER),
                project_id=project.id).order_by('-request_datetime')

            self.assertTrue(da_req)
            self.assertTrue(
                any(d.data_use_purpose == msg_purpose for d in da_req),
                msg_purpose)

            # submitter should receive a notification, requester a confirmation
            self.assertEqual(len(mail.outbox), mail_outbox_size + 2)
            self.assertIn('New Data Access Request', mail.outbox[-2].subject)

            # submitter should see task in project home
            logged_in = self.client.login(username=self.SUBMITTER,
                                          password=self.PASSWORD)
            self.assertTrue(logged_in)

            response = self.client.get(reverse('project_home'))
            self.assertContains(response, "Pending data use request", html=True)

            return da_req

        def accept_request(da_req):
            mail_outbox_size = len(mail.outbox)

            # submitter accepts with comment
            self.client.post(reverse('data_access_request_view', args=(
                project.slug, project.version, da_req.first().id)),
                             data={'proj-status': [
                                 str(DataAccessRequest.ACCEPT_REQUEST_VALUE)],
                                 'proj-duration': ['14'],
                                 'proj-responder_comments': ['great!'],
                                 'data_access_response': [str(da_req[0].id)]}
                             )

            # requester should receive an email
            self.assertEqual(len(mail.outbox), mail_outbox_size + 1)
            self.assertIn('Data Access Request Decision',
                          mail.outbox[-1].subject)


        logged_in = self.client.login(username=self.REQUESTER,
                                      password=self.PASSWORD)
        self.assertTrue(logged_in)

        project = PublishedProject.objects.get(title=self.PROJECT_NAME)
        response = self.client.get(
            reverse('published_project', args=(project.slug, project.version,)))
        # requester shouldn't see files, but a link to form to request access
        self.assertContains(response, "request to the authors")

        # requester fills in form
        da_req = submit_request('I would like ...')

        accept_request(da_req)

        response = self.client.get(reverse('data_access_requests_overview',
                                           args=(
                                           project.slug, project.version,)))
        self.assertContains(response, "1 accepted requests")

        logged_in = self.client.login(username=self.REQUESTER,
                                      password=self.PASSWORD)
        self.assertTrue(logged_in)

        # requester should see the files now
        project = PublishedProject.objects.get(title=self.PROJECT_NAME)
        response = self.client.get(
            reverse('published_project', args=(project.slug, project.version,)))
        self.assertContains(response, "Access the files")

        # additional requests
        da_req_additional = submit_request('Furthermore, I would like to...')

        accept_request(da_req_additional)

        # should have two accepted requests now
        self.assertEqual(len(DataAccessRequest.objects.filter(
            requester_id=User.objects.get(username=self.REQUESTER),
            project_id=project.id,
            status=DataAccessRequest.ACCEPT_REQUEST_VALUE)), 2)


class TestInviteDataAccessReviewer(TestMixin):
    SUBMITTER = 'george'
    ADDITIONAL_REVIEWER = 'admin'
    ADDITIONAL_AUTHOR = 'aewj'

    PASSWORD = 'Tester11!'

    PROJECT_NAME = "Self Managed Access Database Demo"

    def _add_additional_author(self, project):
        author = PublishedAuthor()
        author.project = project
        author.display_order = 2
        author.is_corresponding = False
        author.is_submitting = False
        author.user = User.objects.get(username=self.ADDITIONAL_AUTHOR)
        author.save()

    def _see_manage_requests_button(self, username):
        self.client.login(username=username,
                          password=self.PASSWORD)

        response = self.client.get(reverse('project_home'))
        return "Requests".encode('UTF-8') in response.content

    def test_appointing(self):
        self.assertFalse(self._see_manage_requests_button(self.ADDITIONAL_REVIEWER))

        self.client.login(username=self.SUBMITTER, password=self.PASSWORD)
        # corresponding author/submitter should see Manage Reviewers button in project home
        self.assertContains(self.client.get(reverse('project_home')), "Manage Reviewers", html=True)

        project = PublishedProject.objects.get(title=self.PROJECT_NAME)
        self.client.post(reverse('manage_data_access_reviewers',
                                 args=(project.slug, project.version,)),
                         data={'reviewer': self.ADDITIONAL_REVIEWER,
                               'invite_reviewer' : ['']})

        reviewer = User.objects.get(username=self.ADDITIONAL_REVIEWER)

        assert DataAccessRequestReviewer.objects.filter(
            project_id=project.id, reviewer_id=reviewer.id).exists()

        self.assertTrue(
            self._see_manage_requests_button(self.ADDITIONAL_REVIEWER))

        # reviewer shouldn't be able to manage other reviewers
        self.assertNotContains(self.client.get(reverse('project_home')),
                            "Manage Reviewers", html=True)

        # check reviewer can access request view
        self.assertContains(self.client.get(reverse('data_access_requests_overview',
                                           args=(
                                           project.slug, project.version,))), '')

        # test self-revocation
        self.client.post(reverse('data_access_requests_overview',
                                 args=(project.slug, project.version,)),
                         data={'stop_review': ['']})

        self.assertFalse(
            self._see_manage_requests_button(self.ADDITIONAL_REVIEWER))

        # add published author
        self._add_additional_author(project)
        self.assertFalse(
            self._see_manage_requests_button(self.ADDITIONAL_AUTHOR))

    def test_self_appointing_not_possible(self):
        project = PublishedProject.objects.get(title=self.PROJECT_NAME)

        self.client.login(username=self.SUBMITTER, password=self.PASSWORD)
        response = self.client.post(
            reverse('manage_data_access_reviewers', args=(project.slug, project.version,)),
            data={'reviewer': self.SUBMITTER, 'invite_reviewer': ['']}
        )

        self.assertContains(response, "is already allowed to review requests!")


class TestGenerateSignedUrl(TestMixin):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse(
            'generate_signed_url',
            kwargs={"project_slug": ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database').slug},
        )
        cls.user_credentials = {'username': 'rgmark@mit.edu', 'password': 'Tester11!'}
        cls.unauthorized_user_credentials = {'username': 'aewj@mit.edu', 'password': 'Tester11!'}
        cls.invalid_size_data_1 = {'size': -10, 'filename': '/random.txt'}
        cls.invalid_size_data_2 = {'size': 'file_size', 'filename': '/random.txt'}
        cls.invalid_size_data_3 = {'filename': '/random.txt'}
        cls.invalid_filename_data_1 = {'size': 250000, 'filename': '/ran dom.txt'}
        cls.invalid_filename_data_2 = {'size': 250000, 'filename': '/random§.txt'}
        cls.invalid_filename_data_3 = {'size': 250000, 'filename': 'random.txt'}
        cls.invalid_filename_data_4 = {'size': 250000, 'filename': '//random.txt'}
        cls.invalid_filename_data_5 = {'size': 250000, 'filename': '/random.txt/'}
        cls.invalid_filename_data_6 = {'size': 250000, 'filename': '/ran//dom.txt'}
        cls.invalid_filename_length_data_1 = {'size': 250000, 'filename': '/invalid' * 100 + '.txt'}
        cls.valid_data = {'size': 250000, 'filename': '/folder1/folder2/random.txt'}

    def test_invalid_size(self):
        self.client.login(**self.user_credentials)

        with self.subTest('A negative file size returns a bad request.'):
            response = self.client.post(self.url, self.invalid_size_data_1, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        with self.subTest('A non-numeric file size returns a bad request.'):
            response = self.client.post(self.url, self.invalid_size_data_2, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        with self.subTest('Missing file size returns a bad request.'):
            response = self.client.post(self.url, self.invalid_size_data_3, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

    def test_invalid_filename(self):
        self.client.login(**self.user_credentials)

        with self.subTest('A filename containing whitespaces returns a bad request.'):
            response = self.client.post(self.url, self.invalid_filename_data_1, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        with self.subTest('A filename containing non-ascii characters returns a bad request.'):
            response = self.client.post(self.url, self.invalid_filename_data_2, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        with self.subTest('A filename without a leading slash returns a bad reqeust.'):
            response = self.client.post(self.url, self.invalid_filename_data_3, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        with self.subTest('A filename with  leading slashes returns a bad reqeust.'):
            response = self.client.post(self.url, self.invalid_filename_data_4, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        with self.subTest('A filename with a trailing slash returns a bad reqeust.'):
            response = self.client.post(self.url, self.invalid_filename_data_5, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        with self.subTest('A filename with an empty segment returns a bad reqeust.'):
            response = self.client.post(self.url, self.invalid_filename_data_6, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        with self.subTest('Non-numeric file size returns a bad request.'):
            response = self.client.post(self.url, self.invalid_size_data_2, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

        with self.subTest('A filename cannot be longer than 256 characters.'):
            response = self.client.post(self.url, self.invalid_filename_length_data_1, format='json')

            self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

    @mock.patch('project.views.generate_signed_url_helper')
    def test_valid_size_and_filename(self, signed_url_mock):
        signed_url_mock.return_value = 'https://example.com'

        self.client.login(**self.user_credentials)
        response = self.client.post(self.url, self.valid_data, format='json')

        signed_url_mock.assert_called_once()
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(json.loads(response.content).get('url'), 'https://example.com')

    @mock.patch('project.views.generate_signed_url_helper')
    def test_unauthorized_access(self, signed_url_mock):
        signed_url_mock.return_value = 'https://example.com'

        self.client.login(**self.unauthorized_user_credentials)
        response = self.client.post(self.url, self.valid_data, format='json')

        signed_url_mock.assert_not_called()
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    def test_invalid_access(self):
        self.client.login(**self.user_credentials)

        # Non-submitting author
        self.client.login(username='george@mit.edu', password='Tester11!')
        with self.subTest('Non Submitting author can not upload files.'):
            project = ActiveProject.objects.get(
                title='Demo software for parsing clinical notes')
            response = self.client.post(
                reverse('generate_signed_url', kwargs={
                    "project_slug": project.slug
                }),
                self.valid_data,
                format='json')

            self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

        # awaiting editor decision
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        with self.subTest('Editor cannot upload files unless the project has been accepted.'):
            response = self.client.post(
                reverse('generate_signed_url',
                        kwargs={
                            "project_slug": ActiveProject.objects.get(title='Demo database project').slug
                        }
                        ),
                self.valid_data,
                format='json'
            )
            self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
