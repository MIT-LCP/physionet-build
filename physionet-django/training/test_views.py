import os
import json
import shutil

from django.conf import settings

from lightwave.views import DBCAL_FILE, ORIGINAL_DBCAL_FILE
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from training.models import OnPlatformTraining, ContentBlock, Quiz, QuizChoice
from user.models import Training


def _force_delete_tree(path):
    """
    Recursively delete a directory tree, including read-only directories.
    """
    if os.path.exists(path):
        # Make each (recursive) subdirectory writable, so that we can
        # delete files from it.
        for subdir, _, _ in os.walk(path):
            os.chmod(subdir, 0o700)
        shutil.rmtree(path)


class TestMixin(TestCase):
    """
    Mixin for test methods

    Because the fixtures are installed and database is rolled back
    before each setup and teardown respectively, the demo test files
    will be created and destroyed after each test also. We want the
    demo files as well as the demo data reset each time, and individual
    test methods such as publishing projects may change the files.

    Note about inheriting: https://nedbatchelder.com/blog/201210/multiple_inheritance_is_hard.html

    """

    def setUp(self):
        """
        Copy demo media files to the testing media root.
        Copy demo static files to the testing effective static root.
        Symlink dbcal file to the testing effective static root.

        Does not run collectstatic. The StaticLiveServerTestCase should
        do that automatically for tests that need it.
        """
        _force_delete_tree(settings.MEDIA_ROOT)
        shutil.copytree(os.path.abspath(os.path.join(settings.DEMO_FILE_ROOT, 'media')),
                        settings.MEDIA_ROOT)

        self.test_static_root = settings.STATIC_ROOT if settings.STATIC_ROOT else settings.STATICFILES_DIRS[0]
        _force_delete_tree(self.test_static_root)
        shutil.copytree(os.path.abspath(os.path.join(settings.DEMO_FILE_ROOT, 'static')),
                        self.test_static_root)

        if os.path.exists(ORIGINAL_DBCAL_FILE):
            os.symlink(ORIGINAL_DBCAL_FILE, DBCAL_FILE)

        # Published project files should have been made read-only at
        # the time of publication
        for topdir in (settings.MEDIA_ROOT, self.test_static_root):
            ppdir = os.path.join(topdir, 'published-projects')
            for dirpath, subdirs, files in os.walk(ppdir):
                if dirpath != ppdir:
                    for f in files:
                        os.chmod(os.path.join(dirpath, f), 0o444)
                    for d in subdirs:
                        os.chmod(os.path.join(dirpath, d), 0o555)

    def tearDown(self):
        """
        Remove the testing media root
        """
        _force_delete_tree(settings.MEDIA_ROOT)
        _force_delete_tree(self.test_static_root)

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

    def make_get_request(self, viewname, reverse_kwargs=None):
        """
        Helper Function.
        Create and set a get request

        - viewname: The view name
        - reverse_kwargs: kwargs of additional url parameters
        """
        self.get_request = self.factory.get(reverse(viewname,
                                                    kwargs=reverse_kwargs))
        self.get_request.user = self.user

    def make_post_request(self, viewname, data, reverse_kwargs=None):
        """
        Helper Function.
        Create and set a get request

        - viewname: The view name
        - data: Dictionary of post parameters
        - reverse_kwargs: Kwargs of additional url parameters
        """
        self.post_request = self.factory.post(reverse(viewname,
                                                      kwargs=reverse_kwargs), data)
        self.post_request.user = self.user
        # Provide the message object to the request because middleware
        # is not supported by RequestFactory
        setattr(self.post_request, 'session', 'session')
        messages = FallbackStorage(self.post_request)
        setattr(self.post_request, '_messages', messages)

    def tst_get_request(self, view, view_kwargs=None, status_code=200,
                        redirect_viewname=None, redirect_reverse_kwargs=None):
        """
        Helper Function.
        Test the get request with the view against the expected status code

        - view: The view function
        - view_kwargs: The kwargs dictionary of additional arguments to put into
          view function aside from request
        - status_code: expected status code of response
        - redirect_viewname: view name of the expected redirect
        - redirect_reverse_kwargs: kwargs dictionary of expected redirect
        """
        if view_kwargs:
            response = view(self.get_request, **view_kwargs)
        else:
            response = view(self.get_request)
        self.assertEqual(response.status_code, status_code)
        if status_code == 302:
            # We don't use assertRedirects because the response has no client
            self.assertEqual(response['location'], reverse(redirect_viewname,
                                                           kwargs=redirect_reverse_kwargs))

    def tst_post_request(self, view, view_kwargs=None, status_code=200,
                         redirect_viewname=None, redirect_reverse_kwargs=None):
        """
        Helper Function.
        Test the post request with the view against the expected status code

        - view: The view function
        - view_kwargs: The kwargs dictionary of additional arguments to put into
          view function aside from request
        - status_code: expected status code of response
        - redirect_viewname: view name of the expected redirect
        - redirect_reverse_kwargs: kwargs dictionary of expected redirect
        """
        if view_kwargs:
            response = view(self.post_request, **view_kwargs)
        else:
            response = view(self.post_request)
        self.assertEqual(response.status_code, status_code)
        if status_code == 302:
            self.assertEqual(response['location'], reverse(redirect_viewname,
                                                           kwargs=redirect_reverse_kwargs))


class TestPlatformTraining(TestMixin):
    """ Test that all views are behaving as expected """

    def setUp(self):
        """Setup for tests"""

        super().setUp()
        self.client.login(username='admin', password='Tester11!')

    def test_take_training_get(self):
        """test if the training page loads"""

        response = self.client.get(reverse("platform_training", kwargs={'training_id': 2}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "training/quiz.html")

    def test_take_training_post_redirect_valid(self):
        """test if the post request to training redirects to the correct page"""

        response = self.client.post(reverse("start_training"), {"training_type": 2})
        self.assertRedirects(response, reverse("platform_training",
                                               kwargs={'training_id': 2}), status_code=302)

    def test_take_training_quiz_post_valid(self):
        """test the quiz post verb"""
        question_answers = '{"1":3,"2":5,"3":12,"4":16}'
        trainings = Training.objects.count()
        response = self.client.post(
            reverse("platform_training", kwargs={'training_id': 2}),
            data={
                'question_answers': question_answers
            }
        )
        self.assertRedirects(response, reverse("edit_training"), status_code=302)
        self.assertEqual(Training.objects.count(), trainings + 1)

    def test_create_op_training_get(self):
        """test if admin can access the training page"""

        response = self.client.get(reverse("op_training"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "console/training_type/index.html")

    def test_create_op_training_post_valid(self):
        """test the post request to create a new training"""

        file_path = os.path.join(settings.BASE_DIR, "training", "fixtures", "example-training-create.json")
        with open(file_path, 'r') as f:
            content = f.read()
            content_json = json.loads(content)
            response = self.client.post(
                reverse("op_training"),
                data={
                    "training_id": -1,
                    "create": ['Submit'],
                    "json_file": SimpleUploadedFile(f.name, content.encode()),
                }
            )
            self.assertRedirects(response, reverse("op_training"), status_code=302)
            results = OnPlatformTraining.objects.filter(training_type__name=content_json['name'])
            self.assertEqual(results.count(), 1)
            return results.first()

    def test_update_op_training_post_valid(self):
        """test the post request to update a training"""

        # create a training
        training = self.test_create_op_training_post_valid()

        file_path = os.path.join(settings.BASE_DIR, "training", "fixtures", "example-training-update.json")
        with open(file_path, 'r') as f:
            content = f.read()
            content_json = json.loads(content)
            response = self.client.post(
                reverse("op_training"),
                data={
                    "training_id": training.training_type_id,
                    "update": ['Submit'],
                    "json_file": SimpleUploadedFile(f.name, content.encode()),
                }
            )

            self.assertRedirects(response, reverse("op_training"), status_code=302)
            results = OnPlatformTraining.objects.filter(training_type__name=content_json['name'])
            self.assertEqual(results.count(), 2)
            self.assertEqual(results.last().version, float(content_json['op_trainings']['version']))
