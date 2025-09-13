# apps/annotations/models.py


class AnnotationCollection(models.Model):
    """
    A collection of annotations that can span multiple projects or be project-specific.
    
    Collections provide a way to group related annotations together, whether they're
    from a single PhysioNet project or span multiple datasets. Examples:

        - "Multi-Dataset Sleep Stages" - sleep annotations across multiple datasets
        - "Research Study XYZ Annotations" - all annotations for a specific study
    """
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey('user.User', on_delete=models.CASCADE)
    created_datetime = models.DateTimeField(auto_now_add=True)
    updated_datetime = models.DateTimeField(auto_now=True)


class AnnotationType(models.Model):
    """
    Defines the contract/schema for a specific type of annotation.
    
    This model acts as a formal contract that specifies:
    - What data structure is required for annotation labels (via label_schema)
    - What location type must be used (via allowed_location_kind)
    - What validation rules apply (via location_schema)
    - What the annotation represents semantically (via name, description)
    
    All annotations of this type must follow this contract. The system enforces
    the contract during validation to ensure consistency and data integrity.
    
    Example:
        An "ECG arrhythmia interval" type might require:
        - TimeseriesIntervalLocation for the "where"
        - Labels with event_type (enum), confidence (0-1), notes (optional)
        - Validation that start < end and coordinates are non-negative
    """
    slug = models.SlugField(max_length=100, unique=True). # e.g., "ecg_interval_label"
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    # JSON Schema for Annotation.labels (semantic labels)
    label_schema = models.JSONField()

    class AllowedLocationType(models.TextChoices):
        TIMESERIES_INTERVAL = 'timeseries_interval', 'Timeseries Interval'
        IMAGE_BBOX = 'image_bbox', 'Image Bbox'
        TEXT_SPAN = 'text_span', 'Text Span'

    allowed_location_kind = models.CharField(
        max_length=40,
        choices=AllowedLocationType.choices,
        default=AllowedLocationType.TIMESERIES_INTERVAL,
    )
    version = models.CharField(max_length=20, default='1.0.0')
    created_datetime = models.DateTimeField(auto_now_add=True)


class Annotation(models.Model):
    """
    An individual annotation instance that anchors to a specific file/record.
    
    An annotation represents a single labeled piece of data, consisting of:
    - An anchor (which file/record it applies to)
    - A location (where within that file/record)
    - Label (what the label means)
    
    The annotation must follow the contract defined by its AnnotationType, which
    specifies the required data structure and validation rules.
    
    Key Components:
    - Anchor: Links to a specific file_path within a project (optional)
    - Location: One-to-one relationship with a concrete Location model (e.g., 
      TimeseriesIntervalLocation for time-based annotations)
    - Labels: JSON data validated against the AnnotationType's label_schema
    - Provenance: Metadata about who created it, using what tool, etc.
    
    Examples:
        - ECG arrhythmia annotation: "afib from sample 1000 to 2000 in record001.wfdb"
        - Image bounding box: "dense region at (x,y) with width/height in scan.dcm"
        - Text span: "medical term from character 150 to 200 in report.txt"
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    collection = models.ForeignKey(AnnotationCollection, on_delete=models.CASCADE, related_name='annotations')
    annotation_type = models.ForeignKey(AnnotationType, on_delete=models.PROTECT, related_name='annotations')

    # Anchor to the file
    project = models.ForeignKey('project.PublishedProject', on_delete=models.CASCADE, null=True, blank=True)
    file_path = models.CharField(max_length=500)
    # file_format = models.CharField(max_length=32, blank=True)  # e.g., "wfdb", "dicom", "png", "txt"

    # Labels: validated by AnnotationType.label_schema
    labels = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey('user.User', on_delete=models.CASCADE, related_name='created_annotations')
    created_datetime = models.DateTimeField(auto_now_add=True)
    updated_datetime = models.DateTimeField(auto_now=True)


class BaseLocation(models.Model):
    """
    Abstract base class for all Location types that define "where" within a file.
    
    Locations specify the spatial, temporal, or textual position of an annotation
    within its anchored file. Each Location type represents a different
    way of describing position, e.g.:
    
    - TimeseriesIntervalLocation: Time-based intervals (e.g., ECG segments)
    - ImageBBoxLocation: Rectangular regions in images (e.g., bounding boxes)
    - TextSpanLocation: Character ranges in text (e.g., named entity spans)
    
    Common fields:
    - coord_system: The coordinate system used (e.g., 'samples', 'seconds', 'pixels')
    - channel: Optional channel identifier (useful for multi-channel data like ECG leads)
    
    Each annotation must have exactly one Location instance that matches the
    AnnotationType's allowed_location_kind. The Location provides the "where"
    component that, combined with the annotation's labels (the "what"),
    forms a complete annotation.
    
    Examples:
        - TimeseriesIntervalLocation: "from sample 1000 to 2000 in lead II"
        - ImageBBoxLocation: "rectangle at (50,100) with size 200x150 pixels"
        - TextSpanLocation: "characters 150-200 in the diagnosis section"
    """
    annotation = models.OneToOneField(
        Annotation, on_delete=models.CASCADE, related_name='location'
    )
    coord_system = models.CharField(max_length=24, blank=True)  # e.g., 'samples','seconds','pixels','char_offset'
    created_datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class TimeseriesIntervalLocation(BaseLocation):
    coord_system = models.CharField(max_length=24, default='samples')
    channel = models.CharField(max_length=32, blank=True)
    start = models.BigIntegerField()
    end = models.BigIntegerField()

class ImageBBoxLocation(BaseLocation):
    coord_system = 'pixels'
    x = models.IntegerField()
    y = models.IntegerField()
    width = models.IntegerField()
    height = models.IntegerField()

class TextSpanLocation(BaseLocation):
    coord_system = 'char_offset'
    begin = models.IntegerField()
    end = models.IntegerField()
    encoding = models.CharField(max_length=16, default='utf-8')