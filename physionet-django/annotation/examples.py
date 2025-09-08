"""
Examples of how to use the JSON schema validation in the annotation app.
"""
import json
from django.contrib.auth import get_user_model
from .models import AnnotationCollection, AnnotationType, Annotation
from .validators import load_annotation_schema

User = get_user_model()


def create_example_annotation_type():
    """
    Create an example AnnotationType with the default annotation schema.
    """
    annotation_type = AnnotationType.objects.create(
        name='Image Bounding Box',
        description='Bounding box annotations for medical images',
        schema=load_annotation_schema(),
        modality='image'
    )
    return annotation_type


def create_example_collection(user):
    """
    Create an example AnnotationCollection.
    """
    collection = AnnotationCollection.objects.create(
        name='Medical Image Annotations',
        description='Collection of bounding box annotations for medical images',
        created_by=user,
        metadata={
            'project': 'lung_nodule_detection',
            'version': '1.0'
        }
    )
    return collection


def create_example_bbox_annotation(collection, annotation_type, user):
    """
    Create an example bounding box annotation.
    """
    annotation_data = {
        "version": "1.0",
        "modality": "image",
        "target": {
            "type": "image",
            "id": "chest_xray_001.jpg",
            "dimensions": {
                "width": 1024,
                "height": 1024
            }
        },
        "coordinate_space": "pixel",
        "label": "lung_nodule",
        "ontology": {
            "system": "SNOMED",
            "code": "27925004",
            "display": "Lung nodule"
        },
        "confidence": 0.95,
        "provenance": {
            "annotator_id": str(user.id),
            "tool": "PhysioNet Annotation Tool",
            "method": "human",
            "timestamp": "2024-01-15T10:30:00Z"
        },
        "qa": {
            "status": "unreviewed"
        },
        "spatial": {
            "type": "bbox",
            "x": 300,
            "y": 250,
            "width": 120,
            "height": 80
        },
        "notes": "Small nodule in right upper lobe"
    }
    
    annotation = Annotation.objects.create(
        collection=collection,
        annotation_type=annotation_type,
        data=annotation_data,
        created_by=user,
        file_path='images/chest_xray_001.jpg'
    )
    return annotation


def create_example_polygon_annotation(collection, annotation_type, user):
    """
    Create an example polygon annotation.
    """
    annotation_data = {
        "version": "1.0",
        "modality": "image",
        "target": {
            "type": "image",
            "id": "chest_xray_002.jpg",
            "dimensions": {
                "width": 1024,
                "height": 1024
            }
        },
        "coordinate_space": "pixel",
        "label": "pneumothorax",
        "confidence": 0.88,
        "spatial": {
            "type": "polygon",
            "points": [
                [400, 200],
                [450, 180],
                [480, 220],
                [460, 280],
                [420, 290],
                [390, 250]
            ]
        }
    }
    
    annotation = Annotation.objects.create(
        collection=collection,
        annotation_type=annotation_type,
        data=annotation_data,
        created_by=user,
        file_path='images/chest_xray_002.jpg'
    )
    return annotation


def create_example_video_annotation(collection, user):
    """
    Create an example video annotation with temporal sequence.
    """
    # Create a video annotation type
    video_annotation_type = AnnotationType.objects.create(
        name='Video Object Tracking',
        description='Object tracking annotations for surgical videos',
        schema=load_annotation_schema(),
        modality='video'
    )
    
    annotation_data = {
        "version": "1.0",
        "modality": "video",
        "target": {
            "type": "video",
            "id": "surgery_001.mp4",
            "dimensions": {
                "width": 1920,
                "height": 1080
            }
        },
        "coordinate_space": "pixel",
        "label": "surgical_instrument",
        "temporal": {
            "start_seconds": 30.5,
            "end_seconds": 45.2
        },
        "spatial": {
            "sequence": [
                {
                    "time_seconds": 30.5,
                    "shape": {
                        "type": "bbox",
                        "x": 800,
                        "y": 400,
                        "width": 100,
                        "height": 50
                    }
                },
                {
                    "time_seconds": 35.0,
                    "shape": {
                        "type": "bbox",
                        "x": 850,
                        "y": 380,
                        "width": 100,
                        "height": 50
                    }
                },
                {
                    "time_seconds": 40.0,
                    "shape": {
                        "type": "bbox",
                        "x": 900,
                        "y": 360,
                        "width": 100,
                        "height": 50
                    }
                }
            ]
        }
    }
    
    annotation = Annotation.objects.create(
        collection=collection,
        annotation_type=video_annotation_type,
        data=annotation_data,
        created_by=user,
        file_path='videos/surgery_001.mp4'
    )
    return annotation


def print_validation_example():
    """
    Example of how to handle validation errors.
    """
    print("JSON Schema Validation Examples")
    print("=" * 40)
    
    # Example of invalid data
    invalid_data = {
        "modality": "image",
        # Missing required 'target' and 'label' fields
        "spatial": {
            "type": "bbox",
            "x": 100,
            "y": 50,
            "width": 150,
            "height": 200
        }
    }
    
    try:
        from .validators import validate_annotation_data
        validate_annotation_data(invalid_data)
        print("✓ Validation passed")
    except Exception as e:
        print(f"✗ Validation failed: {e}")
    
    # Example of valid data
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
    
    try:
        from .validators import validate_annotation_data
        validate_annotation_data(valid_data)
        print("✓ Validation passed for valid data")
    except Exception as e:
        print(f"✗ Validation failed: {e}")


if __name__ == "__main__":
    print_validation_example()
