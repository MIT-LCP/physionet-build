import json
from django.utils import timezone
from datetime import timedelta

from project.models import PublishedProject, AccessPolicy, ProjectType, CoreProject
from annotation.models import AnnotationCollection, AnnotationType
from annotation.views import AnnotationCreateAPIView
from annotation.views import (
    AnnotationCollectionCreateAPIView,
    AnnotationTypeCreateAPIView,
)
from user.models import User

from django.test import RequestFactory, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate, APIClient
from oauth2_provider.models import get_access_token_model, get_application_model
from oauth2_provider.settings import oauth2_settings
from django.urls import reverse

Application = get_application_model()
AccessToken = get_access_token_model()

CLEARTEXT_SECRET = "1234567890abcdefghijklmnopqrstuvwxyz"


class BaseTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="oauth_test_user",
            email="oauth_test@example.com",
            password="123456",
        )
        self.resource_type = ProjectType.objects.create(id="32707", name="TestType")
        self.application = Application.objects.create(
            name="Test Application",
            redirect_uris="http://localhost http://example.com http://example.org",
            user=self.user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret=CLEARTEXT_SECRET,
        )
        self.oauth2_settings = oauth2_settings
        self.core_project = CoreProject.objects.create()
        self.project = PublishedProject.objects.create(
            slug="test-project",
            version="1.0.0",
            title="Test Project",
            abstract="Test abstract",
            access_policy=AccessPolicy.CREDENTIALED,
            resource_type=self.resource_type,
            core_project=self.core_project,
        )

    def _create_authorization_header(self, token):
        return "Bearer {0}".format(token)

    def _create_annotation_collection(self):
        """
        Helper function to create annotation collection
        """
        data = {
            "slug": "test-collection",
            "name": "Test Annotation Collection",
            "description": "Base test collection",
        }

        response = self.client.post(
            reverse("annotation:annotation-collection-create"),
            data=data,
            format="json",
            HTTP_AUTHORIZATION=self.auth_header,
        )
        return response

    def _create_annotation_type(self):
        """
        Helper function to create annotation type
        """
        data = {
            "name": "Test Annotation Type",
            "description": "Base test type",
            "slug": "test-annotation-type",
            "label_schema": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["label"],
            },
            "allowed_location_type": "text_span",
        }
        request = self.client.post(
            reverse("annotation:annotation-type-create"),
            data=data,
            format="json",
            HTTP_AUTHORIZATION=self.auth_header,
        )
        return request

    def _create_annotation(self, data):
        """
        Helper function to create annotation
        """
        response = self.client.post(
            reverse("annotation:annotation-create-view", args=[self.collection.slug]),
            data=data,
            format="json",
            HTTP_AUTHORIZATION=self.auth_header,
        )
        return response


class AnnotationAPITests(BaseTest):
    """
    Tests for the Annotation API endpoints, including creation of annotation collections,
    annotation types, and annotations using simulated API requests.
    These tests verify correct API behavior and data validation.
    """

    def test_create_annotation_collection_correct_scope(self):
        self.access_token = AccessToken.objects.create(
            user=self.user,
            scope="annotations:edit",
            expires=timezone.now() + timedelta(seconds=300),
            token="secret-access-token-key",
            application=self.application,
        )
        self.auth_header = self._create_authorization_header(self.access_token.token)
        response = self._create_annotation_collection()
        self.assertEqual(response.status_code, 201)
        response = response.json()
        self.assertEqual(response["slug"], "test-collection")
        self.assertEqual(response["name"], "Test Annotation Collection")
        self.assertEqual(response["description"], "Base test collection")
        self.assertEqual(response["created_by"], self.user.id)

    def test_create_annotation_collection_wrong_scope(self):
        self.access_token = AccessToken.objects.create(
            user=self.user,
            scope="annotations:view",
            expires=timezone.now() + timedelta(seconds=300),
            token="secret-access-token-key",
            application=self.application,
        )
        self.auth_header = self._create_authorization_header(self.access_token.token)
        response = self._create_annotation_collection()
        self.assertEqual(response.status_code, 403)
        response = response.json()

    def test_create_annotation_collection_no_scope(self):
        self.access_token = AccessToken.objects.create(
            user=self.user,
            scope="",
            expires=timezone.now() + timedelta(seconds=300),
            token="secret-access-token-key",
            application=self.application,
        )
        self.auth_header = self._create_authorization_header(self.access_token.token)
        response = self._create_annotation_collection()
        self.assertEqual(response.status_code, 403)
        response = response.json()

    def test_create_annotation_type_correct_scope(self):
        self.access_token = AccessToken.objects.create(
            user=self.user,
            scope="annotations:edit",
            expires=timezone.now() + timedelta(seconds=300),
            token="secret-access-token-key",
            application=self.application,
        )
        self.auth_header = self._create_authorization_header(self.access_token.token)
        response = self._create_annotation_type()
        self.assertEqual(response.status_code, 201)
        response = response.json()
        self.assertEqual(response["slug"], "test-annotation-type")
        self.assertEqual(
            response["label_schema"],
            {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["label"],
            },
        )
        self.assertEqual(response["allowed_location_type"], "text_span")

    def test_create_annotation_text_span_correct_scope(self):
        """
        Test create annotation with text span location
        """
        self.collection = AnnotationCollection.objects.create(
            slug="test-collection-text-span",
            name="Test Collection Text Span",
            description="Test Description",
            created_by=self.user,
        )
        self.annotation_type = AnnotationType.objects.create(
            slug="test-annotation-type-text-span",
            name="Test Annotation Type Text Span",
            description="Test Description",
            label_schema={
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["label"],
            },
            allowed_location_type="text_span",
        )
        text_span_annotation_data = {
            "annotation_type": self.annotation_type.slug,
            "project": self.project.slug,
            "file_path": "../test-filepath.txt",
            "labels": {"label": "Test Label", "confidence": 0.5},
            "location": {
                "location_type": "text_span",
                "coord_system": "char_offset",
                "begin": 100,
                "end": 200,
            },
        }

        self.access_token = AccessToken.objects.create(
            user=self.user,
            scope="annotations:edit",
            expires=timezone.now() + timedelta(seconds=300),
            token="secret-access-token-key",
            application=self.application,
        )
        self.auth_header = self._create_authorization_header(self.access_token.token)
        response = self._create_annotation(data=text_span_annotation_data)
        self.assertEqual(response.status_code, 201)
        response = response.json()
        self.assertEqual(response["file_path"], "../test-filepath.txt")
        self.assertEqual(response["labels"], {"label": "Test Label", "confidence": 0.5})
        # Testing text span setting
        self.assertEqual(response["location"]["location_type"], "text_span")
        self.assertEqual(response["location"]["coord_system"], "char_offset")
        self.assertEqual(response["location"]["begin"], 100)
        self.assertEqual(response["location"]["end"], 200)

    def test_create_annotation_image_bbox(self):
        """
        Test create annotation with image bbox location
        """
        self.collection = AnnotationCollection.objects.create(
            slug="test-collection-bbox",
            name="Test Collection BBox",
            description="Test Description",
            created_by=self.user,
        )
        self.annotation_type = AnnotationType.objects.create(
            slug="test-annotation-type-bbox",
            name="Test Annotation Type BBox",
            description="Test Description",
            label_schema={
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["label"],
            },
            allowed_location_type="image_bbox",
        )
        image_bbox_annotation_data = {
            "annotation_type": self.annotation_type.slug,
            "project": self.project.slug,
            "file_path": "../test-image.png",
            "labels": {"label": "Test Label", "confidence": 0.8},
            "location": {
                "location_type": "image_bbox",
                "coord_system": "pixels",
                "x": 50,
                "y": 100,
                "width": 200,
                "height": 150,
            },
        }
        self.access_token = AccessToken.objects.create(
            user=self.user,
            scope="annotations:edit",
            expires=timezone.now() + timedelta(seconds=300),
            token="secret-access-token-key",
            application=self.application,
        )
        self.auth_header = self._create_authorization_header(self.access_token.token)
        response = self._create_annotation(data=image_bbox_annotation_data)
        self.assertEqual(response.status_code, 201)
        response = response.json()
        self.assertEqual(response["file_path"], "../test-image.png")
        self.assertEqual(response["labels"], {"label": "Test Label", "confidence": 0.8})
        # Testing image bbox setting
        self.assertEqual(response["location"]["location_type"], "image_bbox")
        self.assertEqual(response["location"]["coord_system"], "pixels")
        self.assertEqual(response["location"]["x"], 50)
        self.assertEqual(response["location"]["y"], 100)
        self.assertEqual(response["location"]["width"], 200)
        self.assertEqual(response["location"]["height"], 150)

    def test_create_annotation_timeseries_interval(self):
        """
        Test create annotation with timeseries interval location
        """
        self.collection = AnnotationCollection.objects.create(
            slug="test-collection-timeseries-interval",
            name="Test Collection Timeseries Interval",
            description="Test Description",
            created_by=self.user,
        )
        self.annotation_type = AnnotationType.objects.create(
            slug="test-annotation-type-timeseries-interval",
            name="Test Annotation Type Timeseries Interval",
            description="Test Description",
            label_schema={
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["label"],
            },
            allowed_location_type="timeseries_interval",
        )
        timeseries_interval_annotation_data = {
            "annotation_type": self.annotation_type.slug,
            "project": self.project.slug,
            "file_path": "../test-ecg-record.wfdb",
            "labels": {"label": "Normal Sinus Rhythm", "confidence": 0.95},
            "location": {
                "location_type": "timeseries_interval",
                "coord_system": "samples",
                "channel": "II",
                "start": 1000,
                "end": 5000,
            },
        }
        self.access_token = AccessToken.objects.create(
            user=self.user,
            scope="annotations:edit",
            expires=timezone.now() + timedelta(seconds=300),
            token="secret-access-token-key",
            application=self.application,
        )
        self.auth_header = self._create_authorization_header(self.access_token.token)
        response = self._create_annotation(data=timeseries_interval_annotation_data)
        self.assertEqual(response.status_code, 201)
        response = response.json()
        self.assertEqual(response["file_path"], "../test-ecg-record.wfdb")
        self.assertEqual(
            response["labels"], {"label": "Normal Sinus Rhythm", "confidence": 0.95}
        )
        # Testing timeseries interval setting
        self.assertEqual(response["location"]["location_type"], "timeseries_interval")
        self.assertEqual(response["location"]["coord_system"], "samples")
        self.assertEqual(response["location"]["channel"], "II")
        self.assertEqual(response["location"]["start"], 1000)
        self.assertEqual(response["location"]["end"], 5000)