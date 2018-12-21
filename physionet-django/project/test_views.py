import os
import pdb
import shutil

from django.conf import settings
from django.test import TestCase, override_settings

from project.models import ActiveProject, PublishedProject


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
        print('SETTIN UP')
        shutil.copytree(os.path.abspath(os.path.join(settings.MEDIA_ROOT, '../demo')),
            settings.MEDIA_ROOT)

    def tearDown(self):
        shutil.rmtree(settings.MEDIA_ROOT)


class TestAccess(TestCase, ProjectTestMixin):
    """
    Test that certain views or content can only be accessed by
    appropriate users

    """
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        self.client.login(username='rgmark@mit.edu', password='Tester11!')

    @prevent_request_warnings
    def test_get_project_views(self):
        """
        Basic test of visiting standard project views

        """
        response = self.client.post(reverse('create_project'),
            data={'title':'Database 1', 'resource_type':0})
        project = ActiveProject.objects.get(title='Database 1')
        self.assertRedirects(response, reverse('project_overview', args=(project.slug,)))

        # Visit all the views of the new project
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 200)

        # Try again with a non-author who cannot access
        self.client.login(username='aewj@mit.edu', password='Tester11!')
        for view in PROJECT_VIEWS:
            response = self.client.get(reverse(view, args=(project.slug,)))
            self.assertEqual(response.status_code, 404)


class TestSubmissionState(TestCase, ProjectTestMixin):

    def test_submittable(self):
        """
        Make sure some projects are and others are not able to be
        submitted.
        """
        self.assertTrue(ActiveProject.objects.get(
            title='MIT-BIH Arrhythmia Database').is_submittable())
        self.assertFalse(ActiveProject.objects.get(
            title='MIMIC-III Clinical Database').is_submittable())


class TestFiles(TestCase, ProjectTestMixin):
    pass
