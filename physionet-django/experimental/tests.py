from django.test import TestCase
from oauth2_provider.settings import oauth2_settings
from user.models import User
from experimental.models import AnnotationCollection, Annotation
from oauth2_provider.models import get_access_token_model, get_application_model
from django.utils import timezone
from datetime import timedelta
import base64
from django.urls import reverse


Application = get_application_model()
AccessToken = get_access_token_model()
CLEARTEXT_SECRET = "1234567890abcdefghijklmnopqrstuvwxyz"

# Create your tests here.
class AnnotationCollectionTests(TestCase):
    def setUp(self, oauth2_settings=oauth2_settings):
        """
        Create a demo user, an OAuth Application and an access token for use in testing.
        """
        self.test_user = User.objects.create_user(
            username="oauth_test_user",
            email="oauth_test@example.com",
            password="123456",
        )
        self.test_user.profile.first_names = "OAuth"
        self.test_user.profile.last_name = "User"
        self.test_user.profile.affiliation = "MIT"
        self.test_user.profile.save()

        self.oauth2_settings = oauth2_settings

        self.application = Application.objects.create(
            name="Test Application",
            redirect_uris="http://localhost http://example.com http://example.org",
            user=self.test_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret=CLEARTEXT_SECRET,
        )

        self.access_token = AccessToken.objects.create(
            user=self.test_user,
            scope="profile:read email:read public_id:read",
            expires=timezone.now() + timedelta(seconds=300),
            token="secret-access-token-key",
            application=self.application,
        )

    def get_auth(self):
        """
        Helper method to retrieve a valid authorization code
        """

        authcode_data = {
            "client_id": self.application.client_id,
            "state": "random_state_string",
            "scope": "profile:read email:read public_id:read",
            "redirect_uri": "http://example.org",
            "response_type": "code",
            "allow": True,
        }

        response = self.client.post(
            reverse("oauth2_provider:authorize"), data=authcode_data
        )
        query_dict = parse_qs(urlparse(response["Location"]).query)
        return query_dict["code"].pop()

    
    def get_basic_auth_header(self, user, password):
        """
        Return a dict containing the correct headers to set to make HTTP Basic
        Auth request
        """
        user_pass = "{0}:{1}".format(user, password)
        auth_string = base64.b64encode(user_pass.encode("utf-8"))
        auth_headers = {
            "HTTP_AUTHORIZATION": "Basic " + auth_string.decode("utf-8"),
        }

        return auth_headers

    def test_create_annotation_collection(self):
        self.client.login(username="oauth_test_user", password="123456")
        collection = AnnotationCollection.objects.create(name='Test Collection', created_by=self.test_user, description='Test Description')
        self.assertEqual(collection.name, 'Test Collection')
        self.assertEqual(collection.created_by, self.test_user)
        self.assertEqual(collection.description, 'Test Description')

    def test_create_annotation_document(self):
        self.client.login(username="oauth_test_user", password="123456")
        collection = AnnotationCollection.objects.create(name='Test Collection', created_by=self.test_user, description='Test Description')
        
        # Create annotation with collection reference - DocumentAnnotationData will be created automatically
        annotation = Annotation.objects.create(
            collection=collection,
            created_by=self.test_user, 
            target_filepath='Test Filepath', 
            target_modality='document',
            annotation_description='Test Description'
        )
        
        # Get the automatically created DocumentAnnotationData
        from experimental.models import DocumentAnnotationData
        annotation_data = DocumentAnnotationData.objects.get(annotation=annotation)
        
        # Update the annotation data with specific values
        annotation_data.target_text = 'Test Target Text'
        annotation_data.label_texts = ['Test Data', 'Test Data 2']
        annotation_data.save()
        
        print("Annotation:", Annotation.objects.values())
        print("DocumentAnnotationData:", DocumentAnnotationData.objects.values())
        self.assertEqual(annotation.collection, collection)
        self.assertEqual(annotation.created_by, self.test_user)
        self.assertEqual(annotation.target_filepath, 'Test Filepath')
        self.assertEqual(annotation.target_modality, 'document')
        self.assertEqual(annotation_data.target_text, 'Test Target Text')
        self.assertEqual(annotation_data.label_texts, ['Test Data', 'Test Data 2'])
        self.assertEqual(annotation.annotation_description, 'Test Description')