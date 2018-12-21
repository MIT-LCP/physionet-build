import logging
import os
import pdb
import shutil

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from project.models import ArchivedProject, ActiveProject, PublishedProject, Author


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


class TestAccess(ProjectTestMixin, TestCase):
    """
    Test that certain views or content in their various states can only
    be accessed by the appropriate users

    """
    fixtures = ['demo-user', 'demo-project']

    @prevent_request_warnings
    def test_presubmission(self):
        """
        Test visiting standard project views before submission

        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')
        project = ActiveProject.objects.get(title='MIT-BIH Arrhythmia Database')
        # Visit all the views of the new project
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 200)

        # Try again with a non-author who cannot access
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 404)

    @prevent_request_warnings
    def test_under_submission(self):
        """
        Test project views while under submission

        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')


    @prevent_request_warnings
    def test_published(self):
        """
        """
        self.client.login(username='rgmark@mit.edu', password='Tester11!')



class TestSubmissionState(ProjectTestMixin, TestCase):
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
        response = self.client.post(reverse('project_overview',
            args=(project.slug,)), data={'delete_project':''})

        # response = self.client.post(reverse('project_overview',
        #     args=(project.slug,)), data={'delete_project':''})

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


class TestFiles(ProjectTestMixin, TestCase):
    pass
