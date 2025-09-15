import requests
import json
from django.test import RequestFactory, TestCase
from annotation.views import AnnotationCollectionCreateAPIView, AnnotationTypeCreateAPIView
from user.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

# Configuration
BASE_URL = "http://localhost:8000"

class AnnotationCollectionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="oauth_test_user",
            email="oauth_test@example.com",
            password="123456",
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
                }
            },
            "allowed_location_kind": "text_span"
        }, format='json')
        return request
    
    def _create_annotation_collection(self):
        request = self.factory.post(f"{BASE_URL}/api/annotations/collection/create/", data={
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
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            }
        })
        self.assertEqual(response.data['allowed_location_kind'], "text_span")
    