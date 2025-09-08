"""
Tests for JSON schema validation in the annotation app.
"""
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from .models import AnnotationCollection, AnnotationType, Annotation
from .validators import load_annotation_schema, validate_annotation_data

User = get_user_model()


class AnnotationValidationTestCase(TestCase):
    """Test JSON schema validation for annotations."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.collection = AnnotationCollection.objects.create(
            name='Test Collection',
            description='A test collection',
            created_by=self.user
        )
        
        # Create annotation type with default schema
        self.annotation_type = AnnotationType.objects.create(
            name='Image Bbox',
            description='Bounding box annotations for images',
            schema=load_annotation_schema(),
            modality='image'
        )
    
    def test_valid_image_annotation(self):
        """Test that a valid image annotation passes validation."""
        valid_data = {
            "version": "1.0",
            "modality": "image",
            "target": {
                "type": "image",
                "id": "test_image.jpg",
                "dimensions": {
                    "width": 800,
                    "height": 600
                }
            },
            "coordinate_space": "pixel",
            "label": "tumor",
            "confidence": 0.95,
            "spatial": {
                "type": "bbox",
                "x": 100,
                "y": 50,
                "width": 150,
                "height": 200
            }
        }
        
        # This should not raise an exception
        annotation = Annotation(
            collection=self.collection,
            annotation_type=self.annotation_type,
            data=valid_data,
            created_by=self.user
        )
        annotation.clean()  # Should pass validation
        annotation.save()
        
        # Check that derived fields are populated
        self.assertEqual(annotation.modality, 'image')
        self.assertEqual(annotation.label_text, 'tumor')
    
    def test_invalid_annotation_missing_required(self):
        """Test that an annotation missing required fields fails validation."""
        invalid_data = {
            "version": "1.0",
            "modality": "image",
            # Missing 'target' and 'label' which are required
            "spatial": {
                "type": "bbox",
                "x": 100,
                "y": 50,
                "width": 150,
                "height": 200
            }
        }
        
        annotation = Annotation(
            collection=self.collection,
            annotation_type=self.annotation_type,
            data=invalid_data,
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError):
            annotation.clean()
    
    def test_invalid_annotation_wrong_spatial_type(self):
        """Test that an annotation with invalid spatial data fails validation."""
        invalid_data = {
            "version": "1.0",
            "modality": "image",
            "target": {
                "type": "image",
                "id": "test_image.jpg",
                "dimensions": {
                    "width": 800,
                    "height": 600
                }
            },
            "label": "tumor",
            "spatial": {
                "type": "invalid_type",  # Invalid spatial type
                "x": 100,
                "y": 50,
                "width": 150,
                "height": 200
            }
        }
        
        annotation = Annotation(
            collection=self.collection,
            annotation_type=self.annotation_type,
            data=invalid_data,
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError):
            annotation.clean()
    
    def test_annotation_type_schema_validation(self):
        """Test that AnnotationType schema validation works."""
        # Valid JSON Schema
        valid_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }
        
        # This should not raise an exception
        annotation_type = AnnotationType(
            name='Test Type',
            schema=valid_schema,
            modality='text'
        )
        annotation_type.clean()
        
        # Invalid JSON Schema
        invalid_schema = {
            "type": "invalid_type",  # Invalid JSON Schema type
            "properties": {
                "name": {"type": "string"}
            }
        }
        
        annotation_type_invalid = AnnotationType(
            name='Invalid Type',
            schema=invalid_schema,
            modality='text'
        )
        
        with self.assertRaises(ValidationError):
            annotation_type_invalid.clean()
    
    def test_load_schema(self):
        """Test that the schema loads correctly."""
        schema = load_annotation_schema()
        self.assertIsInstance(schema, dict)
        self.assertIn('$schema', schema)
        self.assertIn('properties', schema)
        self.assertIn('modality', schema['properties'])
        self.assertIn('target', schema['properties'])
        self.assertIn('label', schema['properties'])


class AnnotationValidatorTestCase(TestCase):
    """Test the annotation validator functions directly."""
    
    def test_validate_annotation_data_valid(self):
        """Test validation of valid annotation data."""
        valid_data = {
            "version": "1.0",
            "modality": "image",
            "target": {
                "type": "image",
                "id": "test.jpg"
            },
            "label": "test_label",
            "spatial": {
                "type": "bbox",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 100
            }
        }
        
        # Should not raise an exception
        validate_annotation_data(valid_data)
    
    def test_validate_annotation_data_invalid(self):
        """Test validation of invalid annotation data."""
        invalid_data = {
            "modality": "image",
            # Missing required fields
        }
        
        with self.assertRaises(ValidationError):
            validate_annotation_data(invalid_data)
