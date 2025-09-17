import requests
import json
from django.test import RequestFactory, TestCase
from annotation.views import AnnotationCollectionCreateAPIView, AnnotationTypeCreateAPIView
from user.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from project.models import PublishedProject, AccessPolicy, ProjectType, CoreProject
from annotation.models import AnnotationCollection, AnnotationType
from annotation.views import AnnotationCreateAPIView


# Configuration
BASE_URL = "http://localhost:8000"

class AnnotationAPITests(TestCase):
    """
    Annotation API Tests: Using APIRequestFactory to simulate API requests to creating
    Annotation Collection, Annotation Type, and Annotation.
    """
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="oauth_test_user",
            email="oauth_test@example.com",
            password="123456",
        )
        self.resource_type = ProjectType.objects.create(
            id=195539, name='TestType'
        )
        self.core_project = CoreProject.objects.create()
        self.project = PublishedProject.objects.create(
            slug='test-project',
            version='1.0.0',
            title='Test Project',
            abstract='Test abstract',
            access_policy=AccessPolicy.CREDENTIALED,
            resource_type=self.resource_type,
            core_project=self.core_project
        )

    def _create_annotation_type(self):
        request = self.factory.post(f"{BASE_URL}/api/annotations/type/create/", data={
            "name": "Test Annotation Type",
            "description": "Base test type",
            "slug": "test-annotation-type",
            "label_schema": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {
                        "type": "number", 
                        "minimum": 0.0,
                        "maximum": 1.0},
                },
                "required": ["label"]
            },
            "allowed_location_type": "text_span"
        }, format='json')
        return request
    
    def _create_annotation_collection(self):
        request = self.factory.post(f"{BASE_URL}/api/annotations/collection/create/", data={
            "slug": "test-collection",
            "name": "Test Annotation Collection",
            "description": "Base test collection"
        }, format='json')
        return request
    
    def test_create_annotation_collection(self):
        request = self._create_annotation_collection()
        force_authenticate(request, user=self.user)
        response = AnnotationCollectionCreateAPIView.as_view()(request)        
        self.assertEqual(response.data['created_by'], self.user.id)

    def test_create_annotation_type(self):
        request = self._create_annotation_type()
        # force_authenticate(request, user=self.user)
        response = AnnotationTypeCreateAPIView.as_view()(request)
        self.assertEqual(response.data['slug'], "test-annotation-type")
        self.assertEqual(response.data['label_schema'], {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {
                        "type": "number", 
                        "minimum": 0.0,
                        "maximum": 1.0},
                },
                "required": ["label"]
            })
        self.assertEqual(response.data['allowed_location_type'], "text_span")
    
    def _create_annotation(self, data):
        request = self.factory.post(f"{BASE_URL}/api/annotations/collections/{self.collection.slug}/", data=data, format='json')
        return request
    
    def test_create_annotation_text_span(self):
        self.collection = AnnotationCollection.objects.create(
            slug="test-collection-text-span",
            name="Test Collection Text Span",
            description="Test Description",
            created_by=self.user
        )
        self.annotation_type = AnnotationType.objects.create(
            slug="test-annotation-type-text-span",
            name="Test Annotation Type Text Span",
            description="Test Description",
            label_schema={
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                },
                "required": ["label"]
            },
            allowed_location_type="text_span",
        )
        text_span_annotation_data = {
            "annotation_type": self.annotation_type.slug,
            "project": self.project.slug,
            "file_path": "../test-filepath.txt",
            "labels": {
                "label": "Test Label",
                "confidence": 0.5
            },
            "location": {
                "location_type": "text_span",
                "coord_system": "char_offset",
                "begin": 100,
                "end": 200
            }
        }
        request = self._create_annotation(data=text_span_annotation_data)
        force_authenticate(request, user=self.user)
        response = AnnotationCreateAPIView.as_view()(request, collection=self.collection.slug)
        # print("Response: ", response.data)
        self.assertEqual(response.data['file_path'], "../test-filepath.txt")
        self.assertEqual(response.data['labels'], {
            "label": "Test Label", 
            "confidence": 0.5
        })
        ## Testing location setting
        self.assertEqual(response.data['location']['location_type'], "text_span")
        self.assertEqual(response.data['location']['coord_system'], "char_offset")
        self.assertEqual(response.data['location']['begin'], 100)
        self.assertEqual(response.data['location']['end'], 200)

    def test_create_annotation_image_bbox(self):
        self.collection = AnnotationCollection.objects.create(
            slug="test-collection-bbox",
            name="Test Collection BBox",
            description="Test Description",
            created_by=self.user
        )
        self.annotation_type = AnnotationType.objects.create(
            slug="test-annotation-type-bbox",
            name="Test Annotation Type BBox",
            description="Test Description",
            label_schema={
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                },
                "required": ["label"]
            },
            allowed_location_type="image_bbox",
        )
        image_bbox_annotation_data = {
            "annotation_type": self.annotation_type.slug,
            "project": self.project.slug,
            "file_path": "../test-image.png",
            "labels": {
                "label": "Test Label",
                "confidence": 0.8
            },
            "location": {
                "location_type": "image_bbox",
                "coord_system": "pixels",
                "x": 50,
                "y": 100,
                "width": 200,
                "height": 150
            }
        }
        request = self._create_annotation(data=image_bbox_annotation_data)
        force_authenticate(request, user=self.user)
        response = AnnotationCreateAPIView.as_view()(request, collection=self.collection.slug)
        # print("Response: ", response.data)
        self.assertEqual(response.data['file_path'], "../test-image.png")
        self.assertEqual(response.data['labels'], {
            "label": "Test Label", 
            "confidence": 0.8
        })
        ## Testing location setting
        self.assertEqual(response.data['location']['location_type'], "image_bbox")
        self.assertEqual(response.data['location']['coord_system'], "pixels")
        self.assertEqual(response.data['location']['x'], 50)
        self.assertEqual(response.data['location']['y'], 100)
        self.assertEqual(response.data['location']['width'], 200)
        self.assertEqual(response.data['location']['height'], 150)
    
    def test_create_annotation_timeseries_interval(self):
        self.collection = AnnotationCollection.objects.create(
            slug="test-collection-timeseries-interval",
            name="Test Collection Timeseries Interval",
            description="Test Description",
            created_by=self.user
        )
        self.annotation_type = AnnotationType.objects.create(
            slug="test-annotation-type-timeseries-interval",
            name="Test Annotation Type Timeseries Interval",
            description="Test Description",
            label_schema={
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
                },
                "required": ["label"]
            },
            allowed_location_type="timeseries_interval",
        )
        timeseries_interval_annotation_data = {
            "annotation_type": self.annotation_type.slug,
            "project": self.project.slug,
            "file_path": "../test-ecg-record.wfdb",
            "labels": {
                "label": "Normal Sinus Rhythm",
                "confidence": 0.95
            },
            "location": {
                "location_type": "timeseries_interval",
                "coord_system": "samples",
                "channel": "II",
                "start": 1000,
                "end": 5000
            }
        }
        request = self._create_annotation(data=timeseries_interval_annotation_data)
        force_authenticate(request, user=self.user)
        response = AnnotationCreateAPIView.as_view()(request, collection=self.collection.slug)
        # print("Response: ", response.data)
        self.assertEqual(response.data['file_path'], "../test-ecg-record.wfdb")
        self.assertEqual(response.data['labels'], {
            "label": "Normal Sinus Rhythm", 
            "confidence": 0.95
        })
        ## Testing location setting
        self.assertEqual(response.data['location']['location_type'], "timeseries_interval")
        self.assertEqual(response.data['location']['coord_system'], "samples")
        self.assertEqual(response.data['location']['channel'], "II")
        self.assertEqual(response.data['location']['start'], 1000)
        self.assertEqual(response.data['location']['end'], 5000)