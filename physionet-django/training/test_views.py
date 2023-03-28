import os
import json
import shutil

from django.conf import settings

from lightwave.views import DBCAL_FILE, ORIGINAL_DBCAL_FILE
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from training.models import Course, ContentBlock, Quiz, QuizChoice
from user.models import Training


class TestPlatformTraining(TestCase):
    """ Test that all views are behaving as expected """

    def setUp(self):
        """Setup for tests"""

        super().setUp()
        self.client.login(username='tompollard', password='Tester11!')

    def test_take_training_get(self):
        """test if the training page loads"""

        # check if the course has been made in-active by any tests and make it active
        course = Course.objects.filter(training_type__slug="world-101-introduction-to-continents-and-countries")
        if course.exists():
            course.update(is_active=True)

        response = self.client.get(reverse(
            "platform_training",
            kwargs={'training_slug': "world-101-introduction-to-continents-and-countries"}
        ))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "training/course.html")

    def test_create_course_get(self):
        """test if admin can access the courses page"""

        response = self.client.get(reverse("courses"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "console/training_type/index.html")

    def test_create_course_post_valid(self):
        """test the post request to create a new course"""

        file_path = os.path.join(settings.BASE_DIR, "static", "sample", "example-course-create.json")
        with open(file_path, 'r') as f:
            content = f.read()
            content_json = json.loads(content)
            response = self.client.post(
                reverse("courses"),
                data={
                    "training_id": -1,
                    "create": ['Submit'],
                    "json_file": SimpleUploadedFile(f.name, content.encode()),
                }
            )
            self.assertRedirects(response, reverse("courses"), status_code=302)
            results = Course.objects.filter(training_type__name=content_json['title'])
            self.assertEqual(results.count(), 1)
            return results.first()

    def test_update_course_post_valid(self):
        """test the post request to update a course"""

        # create a training
        training = self.test_create_course_post_valid()

        file_path = os.path.join(settings.BASE_DIR, "static", "sample", "example-course-update.json")
        with open(file_path, 'r') as f:
            content = f.read()
            content_json = json.loads(content)
            response = self.client.post(
                reverse("course_details", kwargs={'training_slug': training.training_type.slug}),
                data={
                    "training_id": training.training_type_id,
                    "update": ['Submit'],
                    "json_file": SimpleUploadedFile(f.name, content.encode()),
                }
            )

            self.assertRedirects(response, reverse("course_details", kwargs={
                'training_slug': training.training_type.slug}), status_code=302)
            results = Course.objects.filter(training_type__name=content_json['title'])
            self.assertEqual(results.count(), 2)
            self.assertEqual(results.last().version, content_json['version'])

    def test_take_platform_training(self):
        """test if the training page loads"""

        response = self.client.get(reverse("platform_training", kwargs={
            'training_slug': "world-101-introduction-to-continents-and-countries"}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "training/course.html")

    def test_current_module_block(self):
        """test if the current module block page loads"""

        response = self.client.get(reverse("current_module_block", kwargs={
            'training_slug': "world-101-introduction-to-continents-and-countries",
            'module_order': 1, 'order': 1}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "training/course_block.html")
