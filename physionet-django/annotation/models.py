from django.db import models
import uuid
from enum import Enum


class AllowedLocationType(Enum):
    """
    Enumeration of supported location types for annotations.

    Defines the spatial/temporal/textual coordinate systems that can be used
    to specify where an annotation is positioned within a data file.
    """
    TIMESERIES_INTERVAL = 'timeseries_interval'
    IMAGE_BBOX = 'image_bbox'
    TEXT_SPAN = 'text_span'

    @classmethod
    def choices(cls):
        return [(choice.value, choice.value.replace('_', ' ').title()) for choice in cls]

class AnnotationCollection(models.Model):
    """
    A collection of related annotations across one or more datasets.

    Collections organize annotations by research context, study, or analytical purpose
    rather than by technical constraints. They enable:
    - Cross-dataset studies (e.g., "Sleep stages across MIT-BIH and SHHS datasets")
    - Research project organization (e.g., "Cardiology Study 2024 annotations")
    - Collaborative annotation workflows (e.g., "Expert consensus labels")
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.CharField(max_length=100, unique=True, null=True)  # e.g., "ecg_interval_collection"
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey('user.User', on_delete=models.CASCADE)
    created_datetime = models.DateTimeField(auto_now_add=True)
    updated_datetime = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [
            (
                "can_publish",
                "Can publish annotation collections",
            ),
            (
                "can_view",
                "Can view annotation collections",
            ),
        ]

class AnnotationType(models.Model):
    """
    Schema definition and validation contract for a specific annotation type.

    This model acts as a formal contract that specifies:
    - What data structure is required for annotation labels (via label_schema)
    - What location type must be used (via allowed_location_type)
    - What the annotation represents semantically (via name, description)

    Example:
        An "ECG arrhythmia interval" type might require:
        - TimeseriesIntervalLocation for the "where"
        - Labels with label (string), confidence (0-1), notes (optional)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.CharField(max_length=100, unique=True)  # e.g., "ecg_interval_label"
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    # JSON Schema for Annotation.labels (semantic labels)
    label_schema = models.JSONField()

    allowed_location_type = models.CharField(
        max_length=40,
        choices=AllowedLocationType.choices(),
        default=AllowedLocationType.TIMESERIES_INTERVAL.value,
    )
    # Schema versioning for evolution and backward compatibility
    version = models.CharField(max_length=20, default='1.0.0')
    created_datetime = models.DateTimeField(auto_now_add=True)


class BaseLocation(models.Model):
    """
    Concrete base class for all Location types that define "where" within a file.

    Locations define the spatial, temporal, or textual coordinates of an annotation
    within its target file. Different location types handle different coordinate systems:

    COORDINATE SYSTEMS:
    - Timeseries: temporal coordinates (samples, seconds, milliseconds)
    - Images: spatial coordinates (pixels, relative positions)
    - Text: character-based coordinates (UTF-8 offsets, line/column)

    Common fields:
    - id: The unique identifier for the location
    - location_type: The type of location (e.g., 'timeseries_interval', 'image_bbox', 'text_span')
    - coord_system: The coordinate system used (e.g., 'samples', 'seconds', 'pixels')
    - created_by: The user who created the location
    - created_datetime: The datetime the location was created

    Each annotation must have exactly one Location instance that matches the
    AnnotationType's allowed_location_kind. The Location provides the "where"
    component that, combined with the annotation's labels (the "what"),
    forms a complete annotation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location_type = models.CharField(
        max_length=40,
        choices=AllowedLocationType.choices(),
        default=AllowedLocationType.TIMESERIES_INTERVAL.value,
    )
    coord_system = models.CharField(max_length=24, blank=True)  # e.g., 'samples','seconds','pixels','char_offset'
    created_by = models.ForeignKey('user.User', on_delete=models.CASCADE)
    created_datetime = models.DateTimeField(auto_now_add=True)


class TimeseriesIntervalLocation(BaseLocation):
    """
    Temporal interval location for time-series data annotations.

    Specifies a contiguous time interval within a time-series recording using
    start and end coordinates. Commonly used for:
    - Physiological events (heart beats, seizures, sleep stages)
    - Signal quality segments (noisy vs clean data regions)
    - Clinical episodes (medication periods, monitoring sessions)

    Example: from seconds 10 to 20 of the EEG recording

    COORDINATE SYSTEMS:
    - 'samples': Digital sample indices (most common for raw signals)
    - 'seconds': Time offsets from recording start
    - 'milliseconds': High-precision timing
    - Custom units as needed by specific datasets
    """
    channel = models.CharField(max_length=32, blank=True)
    start = models.BigIntegerField()
    end = models.BigIntegerField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.coord_system:
            self.coord_system = 'samples'


class ImageBBoxLocation(BaseLocation):
    """
    Rectangular bounding box location for 2D image annotations.

    Defines a rectangular region within an image using top-left corner coordinates
    and dimensions. Commonly used for:
    - Medical imaging ROIs (lesions, anatomical structures)
    - Object detection (instruments, landmarks)
    - Image quality assessment (artifact regions)

    Example: a lesion at (50,100) with size 200x150 pixels

    COORDINATE SYSTEMS:
    - 'pixels': Absolute pixel coordinates (most common)
    - 'relative': Normalized coordinates (0.0-1.0 range)
    - 'mm': Physical measurements for calibrated medical images
    """
    x = models.IntegerField()
    y = models.IntegerField()
    width = models.IntegerField()
    height = models.IntegerField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.coord_system:
            self.coord_system = 'pixels'


class TextSpanLocation(BaseLocation):
    """
    Character span location for text-based annotations.

    Defines a contiguous character range within a text document using start and
    end character offsets. Commonly used for:
    - Clinical NLP (named entities, medical terms, symptoms)
    - Report section identification (diagnosis, treatment, history)
    - Text quality assessment (errors, ambiguities)

    Example: characters 150-200 in the diagnosis section of a medical report

    COORDINATE SYSTEMS:
    - 'char_offset': Unicode character positions (default)
    - 'byte_offset': Raw byte positions for specific encodings
    - 'token_offset': Word/token-based positions
    """
    begin = models.IntegerField()
    end = models.IntegerField()
    encoding = models.CharField(max_length=16, default='utf-8')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.coord_system:
            self.coord_system = 'char_offset'


class Annotation(models.Model):
    """
    Individual annotation instance linking semantic labels to file locations.

    Represents a single labeled data point consisting of three components:

    1. ANCHOR: Which file/record the annotation applies to (project + file_path)
    2. LOCATION: Where within that file (via OneToOne relationship to BaseLocation)
    3. LABELS: What the annotation means (semantic data validated by AnnotationType)

    VALIDATION CONTRACTS:
    - Must conform to AnnotationType's label_schema (semantic validation)
    - Location type must match AnnotationType's allowed_location_type

    Example: ECG Annotation:
        - project: "mitdb/1.0.0", file_path: "100.dat"
        - location: TimeseriesIntervalLocation(start=1000, end=2000, channel="II")
        - labels: {"rhythm": "atrial_fibrillation", "confidence": 0.95}
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    collection = models.ForeignKey(AnnotationCollection, on_delete=models.CASCADE, related_name='collection_slug')
    annotation_type = models.ForeignKey(AnnotationType, on_delete=models.PROTECT, related_name='annotation_type_slug')

    # Anchor to the file
    project = models.ForeignKey(
        'project.PublishedProject',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='project_slug')
    file_path = models.CharField(max_length=500)

    # Labels: validated by AnnotationType.label_schema
    labels = models.JSONField(default=dict, blank=True)

    location = models.OneToOneField(
        BaseLocation, on_delete=models.CASCADE, related_name='location'
    )
    created_by = models.ForeignKey('user.User', on_delete=models.CASCADE)
    created_datetime = models.DateTimeField(auto_now_add=True)
    updated_datetime = models.DateTimeField(auto_now=True)
