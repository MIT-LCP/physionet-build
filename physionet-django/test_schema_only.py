#!/usr/bin/env python3
"""
Test just the JSON schema validation without Django.
Run with: python test_schema_only.py
"""
import json
import jsonschema
from jsonschema import validate, ValidationError

def load_schema():
    """Load the annotation schema"""
    with open('annotation/schemas/annotation.schema.json', 'r') as f:
        return json.load(f)

def test_schema_validation():
    """Test schema validation with various examples"""
    print("🔍 Testing JSON Schema Validation")
    print("=" * 40)
    
    schema = load_schema()
    print(f"✅ Loaded schema with modalities: {schema['properties']['modality']['enum']}")
    
    test_cases = [
        # Valid image annotation
        {
            "name": "Valid Image Annotation",
            "data": {
                "modality": "image",
                "target": {
                    "type": "image",
                    "id": "chest_xray.jpg",
                    "dimensions": {"width": 1024, "height": 768}
                },
                "label": "pneumonia",
                "spatial": {
                    "type": "bbox",
                    "x": 100, "y": 150,
                    "width": 200, "height": 180
                },
                "confidence": 0.85
            },
            "should_pass": True
        },
        
        # Valid video annotation
        {
            "name": "Valid Video Annotation",
            "data": {
                "modality": "video",
                "target": {"type": "video", "id": "surgery.mp4"},
                "label": "incision",
                "spatial": {"type": "polygon", "points": [[10,10], [20,10], [15,20]]},
                "temporal": {"start_seconds": 45.2, "end_seconds": 52.8}
            },
            "should_pass": True
        },
        
        # Valid text annotation
        {
            "name": "Valid Text Annotation", 
            "data": {
                "modality": "text",
                "target": {
                    "type": "document",
                    "id": "clinical_note.txt",
                    "text_span": {"start": 100, "end": 120}
                },
                "label": "medication"
            },
            "should_pass": True
        },
        
        # Valid label annotation
        {
            "name": "Valid Label Annotation",
            "data": {
                "modality": "label",
                "target": {"type": "study", "id": "study_001"},
                "label": "abnormal"
            },
            "should_pass": True
        },
        
        # Invalid: missing required field
        {
            "name": "Invalid - Missing Label",
            "data": {
                "modality": "image",
                "target": {"type": "image", "id": "test.jpg"},
                "spatial": {"type": "bbox", "x": 0, "y": 0, "width": 100, "height": 100}
                # Missing required 'label' field
            },
            "should_pass": False
        },
        
        # Invalid: image without spatial
        {
            "name": "Invalid - Image Missing Spatial",
            "data": {
                "modality": "image",
                "target": {"type": "image", "id": "test.jpg"},
                "label": "test_label"
                # Missing required 'spatial' field for image
            },
            "should_pass": False
        },
        
        # Invalid: wrong modality/target combination
        {
            "name": "Invalid - Wrong Target Type for Modality",
            "data": {
                "modality": "image", 
                "target": {"type": "video", "id": "test.mp4"},  # Wrong target type
                "label": "test",
                "spatial": {"type": "bbox", "x": 0, "y": 0, "width": 100, "height": 100}
            },
            "should_pass": False
        }
    ]
    
    passed = 0
    total = len(test_cases)
    
    for test_case in test_cases:
        try:
            validate(instance=test_case["data"], schema=schema)
            if test_case["should_pass"]:
                print(f"✅ {test_case['name']}")
                passed += 1
            else:
                print(f"❌ {test_case['name']} - Should have failed but passed!")
        except ValidationError as e:
            if not test_case["should_pass"]:
                print(f"✅ {test_case['name']} - Correctly rejected")
                passed += 1
            else:
                print(f"❌ {test_case['name']} - Should have passed but failed:")
                print(f"   Error: {e.message}")
        except Exception as e:
            print(f"❌ {test_case['name']} - Unexpected error: {e}")
    
    print("\n" + "=" * 40)
    print(f"📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All schema validation tests passed!")
        print("✅ Your JSON schema is working correctly!")
    else:
        print("⚠️  Some tests failed - check your schema")
    
    return passed == total

if __name__ == '__main__':
    test_schema_validation()

