import logging
import os
import pdb
import shutil

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from project.models import ArchivedProject, ActiveProject, PublishedProject, Author, AuthorInvitation, License


def prevent_request_warnings(original_function):
    """
    Decorator to prevent request class from throwing warnings for 404s.

    """
    def new_function(*args, **kwargs):
        # raise logging level to ERROR
        logger = logging.getLogger('django.request')
        previous_logging_level = logger.getEffectiveLevel()
        logger.setLevel(logging.ERROR)
        # trigger original function that would throw warning
        original_function(*args, **kwargs)
        # lower logging level back to previous
        logger.setLevel(previous_logging_level)

    return new_function


PROJECT_VIEWS = [
    'project_overview', 'project_authors', 'project_metadata',
    'project_access', 'project_identifiers', 'project_files',
    'project_proofread', 'project_preview', 'project_submission'
]


class ProjectTestMixin():
    """
    Class with mixin methods to inherit for test classes.

    Because the fixtures are installed and database is rolled back
    before each setup and teardown respectively, the demo test files
    will be created and destroyed after each test also. We want the
    demo files as well as the demo data reset each time, and individual
    test methods such as publishing projects may change the files.

    Note about inheriting: https://nedbatchelder.com/blog/201210/multiple_inheritance_is_hard.html
    """
    def setUp(self):
        """
        Copy the demo files to the testing root
        """
        shutil.copytree(os.path.abspath(os.path.join(settings.MEDIA_ROOT, '../demo')),
            settings.MEDIA_ROOT)

    def tearDown(self):
        """
        Remove the testing media root
        """
        shutil.rmtree(settings.MEDIA_ROOT)

    def assertMessage(self, response, level):
        """
        Assert that the max message level in the request equals `level`.

        Can use message success or error to test outcome, since there
        are different cases where forms are reloaded, not present, etc.

        The response code for invalid form submissions are still 200
        so cannot use that to test form submissions.

        """
        self.assertEqual(max(m.level for m in response.context['messages']),
            level)


class TestPrepareSubmission(ProjectTestMixin, TestCase):
    """
    Test views/functions that edit project content for submission

    """
    fixtures = ['demo-user', 'demo-project']

    @prevent_request_warnings
    def test_author(self):
        """
        Test visiting standard project views before submission

        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        # Visit all the views of the new project
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 200)


class TestAccessPresubmission(ProjectTestMixin, TestCase):
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


class TestAccessUnderSubmission(ProjectTestMixin, TestCase):
    """
    Test that certain views or content in their various states can only
    be accessed by the appropriate users.

    Projects under submission.

    """
    fixtures = ['demo-user', 'demo-project']

    @prevent_request_warnings
    def test_visit_get(self):
        """

        """
        pass



class TestAccessPublished(ProjectTestMixin, TestCase):
    """
    Test that certain views or content in their various states can only
    be accessed by the appropriate users.

    Published projects.

    """
    fixtures = ['demo-user', 'demo-project']

    @prevent_request_warnings
    def test_visit_get(self):
        """

        """
        pass



class TestState(ProjectTestMixin, TestCase):
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
        author_id = project.authors.all().first().id
        # response = self.client.post(reverse('project_metadata',
        #     args=(project.slug,)), data={'title':'Database 1'})
        # 'Delete' (archive) the project
        response = self.client.post(reverse('project_overview',
            args=(project.slug,)), data={'delete_project':''})
        # The ActiveProject model should be replaced, and all its
        # related objects should point to the new ArchivedProject
        self.assertFalse(ActiveProject.objects.filter(title='Database 1'))
        project = ArchivedProject.objects.get(title='Database 1')
        self.assertTrue(Author.objects.get(id=author_id).project == project)
        self.assertTrue(project.abstract == 'abstract')

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
        pass

    def test_publish(self):
        pass



class TestInteraction(ProjectTestMixin, TestCase):


    fixtures = ['demo-user', 'demo-project']

    def test_storage_request(self):
        """
        """
        pass

    def test_invite_author(self):
        """
        """
        pass
