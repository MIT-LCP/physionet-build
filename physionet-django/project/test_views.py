import os
import pdb

from django.contrib.staticfiles.templatetags.staticfiles import static
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from project.models import (ArchivedProject, ActiveProject, PublishedProject,
    Author, AuthorInvitation, License, StorageRequest)
from user.test_views import prevent_request_warnings, TestMixin


PROJECT_VIEWS = [
    'project_overview', 'project_authors', 'project_metadata',
    'project_access', 'project_discovery', 'project_files',
    'project_proofread', 'project_preview', 'project_submission'
]


class TestAccessPresubmission(TestMixin, TestCase):
    """
    Test that certain views or content in their various states can only
    be accessed by the appropriate users.

    Projects in presubmission state.

    """
    fixtures = ['demo-user', 'demo-project']

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
        response = self.client.get(reverse('serve_project_file', args=(project.slug, 'notes/notes.txt')))
        self.assertEqual(response.status_code, 200)

        # Visit as project coauthor
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('serve_project_file', args=(project.slug, 'notes/notes.txt')))
        self.assertEqual(response.status_code, 200)

        # Visit as non-author
        self.client.login(username='george@mit.edu', password='Tester11!')
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse('serve_project_file', args=(project.slug, 'notes/notes.txt')))
        self.assertEqual(response.status_code, 404)

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
        open_data_license = License.objects.filter(access_policy=0, resource_type=0).first()
        restricted_data_license = License.objects.filter(access_policy=1, resource_type=0).first()
        software_license = License.objects.filter(resource_type=1).first()

        response = self.client.post(reverse(
            'project_access', args=(project.slug,)),
            data={'access_policy':0, 'license':open_data_license.id})
        self.assertMessage(response, 25)

        response = self.client.post(reverse(
            'project_access', args=(project.slug,)),
            data={'access_policy':0, 'license':restricted_data_license.id})
        self.assertMessage(response, 40)

        response = self.client.post(reverse(
            'project_access', args=(project.slug,)),
            data={'access_policy':0, 'license':software_license.id})
        self.assertMessage(response, 40)

        # Non-submitting author is not allowed
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        response = self.client.post(reverse(
            'project_access', args=(project.slug,)),
            data={'access_policy':0, 'license':open_data_license.id})
        self.assertEqual(response.status_code, 404)

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
        # Existing items
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'delete_items':'', 'subdir':'notes', 'items':['ICUSTAYS.csv.gz', 'PATIENTS.csv.gz']})
        self.assertMessage(response, 25)
        self.assertFalse(os.path.isfile(os.path.join(project.file_root(), 'notes', 'ICUSTAYS.csv.gz')))
        self.assertFalse(os.path.isfile(os.path.join(project.file_root(), 'notes', 'PATIENTS.csv.gz')))

        # Upload file. Use same file content already existing.
        with open(os.path.join(project.file_root(), 'D_ITEMS.csv.gz'), 'rb') as f:
            response = self.client.post(reverse(
                'project_files', args=(project.slug,)),
                data={'upload_files':'', 'subdir':'notes',
                      'file_field':SimpleUploadedFile(f.name, f.read())})
        self.assertMessage(response, 25)
        self.assertEqual(
            open(os.path.join(project.file_root(), 'D_ITEMS.csv.gz'), 'rb').read(),
            open(os.path.join(project.file_root(), 'notes/D_ITEMS.csv.gz'), 'rb').read())

        # Non-submitting author cannot post
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        response = self.client.post(reverse(
            'project_files', args=(project.slug,)),
            data={'create_folder':'', 'folder_name':'new-folder-valid'})
        self.assertEqual(response.status_code, 404)


class TestAccessPublished(TestMixin, TestCase):
    """
    Test that certain views or content in their various states can only
    be accessed by the appropriate users.

    Published projects.

    """
    fixtures = ['demo-user', 'demo-project']

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
            'serve_protected_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 404)

        # Non-credentialed user
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        response = self.client.get(reverse(
            'serve_protected_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 404)

        # Credentialed user that has not signed dua
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        response = self.client.get(reverse(
            'serve_protected_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 404)

        # Sign the dua and get file again
        response = self.client.post(reverse('sign_dua',
            args=(project.slug, project.version,)),
            data={'agree':''})
        response = self.client.get(reverse(
            'serve_protected_project_file',
            args=(project.slug, project.version, 'SHA256SUMS.txt')))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse(
            'serve_protected_project_file',
            args=(project.slug, project.version, 'admissions.csv')))
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
        response = self.client.get(static('published-projects/{}/{}/Makefile'.format(project.slug, project.version)))
        self.assertEqual(response.status_code, 200)


class TestState(TestMixin, TestCase):
    """
    Test that all objects are in their intended states, during and
    after review/publication state transitions.

    """
    fixtures = ['demo-user', 'demo-project']

    def test_create_archive(self):
        """
        Create and archive a project
        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        response = self.client.post(reverse('create_project'),
            data={'title':'Database 1', 'resource_type':0, 'abstract':'abstract'})

        project = ActiveProject.objects.get(title='Database 1')
        self.assertRedirects(response, reverse('project_overview',
            args=(project.slug,)))
        self.assertEqual(project.authors.all().get().user.email, 'rgmark@mit.edu')

    def test_archive(self):
        """
        Archive a project
        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        author_id = project.authors.all().first().id
        abstract = project.abstract
        # 'Delete' (archive) the project
        response = self.client.post(reverse('project_overview',
            args=(project.slug,)), data={'delete_project':''})
        # The ActiveProject model should be replaced, and all its
        # related objects should point to the new ArchivedProject
        self.assertFalse(ActiveProject.objects.filter(title='MIT-BIH Arrhythmia Database'))
        project = ArchivedProject.objects.get(title='MIT-BIH Arrhythmia Database')
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


class TestInteraction(TestMixin, TestCase):
    """
    Test project views that require multiple user interaction that are
    not directly related to reviewing/editing the project.

    """

    fixtures = ['demo-user', 'demo-project']

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
