import requests
import json
from django.test import RequestFactory, TestCase
from annotation.views import AnnotationCollectionCreateAPIView
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
    
    def test_create_annotation_collection(self):
        request = self.factory.post(f"{BASE_URL}/api/annotations/collection/create/", data={
            "name": "Test Annotation Collection",
            "description": "Base test collection"
        }, format='json')
        force_authenticate(request, user=self.user)
        
        # Print user details to verify
        print(f"Test user ID: {self.user.id}")
        print(f"Test user username: {self.user.username}")
        
        response = AnnotationCollectionCreateAPIView.as_view()(request)
        print(f"Response data: {response.data}")
        
        # Verify the created_by matches the test user
        self.assertEqual(response.data['created_by'], self.user.id)