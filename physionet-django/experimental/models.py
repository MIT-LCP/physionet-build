from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver

from project.modelcomponents.fields import SafeHTMLField
from project.validators import validate_title, validate_version

# Create your models here.

class AnnotationCollection(models.Model):
    """
    AnnotationCollection defines the collection of Annotation objects.
    """
    name = models.CharField(max_length=200)
    description = SafeHTMLField(blank=True)
    created_by = models.ForeignKey('user.User', on_delete=models.CASCADE, related_name='experimental_annotation_collections')
    created_datetime = models.DateTimeField(auto_now_add=True)
    updated_datetime = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ('add', 'delete', 'change')

    def __str__(self):
        return self.name

## Defining the Annotation and Modalities Supported
class Annotation(models.Model):
    """
    Individual Annotation object in an AnnotationCollection with an AnnotationType.
    Each Annotation has its own AnnotationType, allowing multiple types per collection.
    """
    collection = models.ForeignKey(AnnotationCollection, on_delete=models.CASCADE, related_name='annotations')
    target_project = models.ForeignKey('project.PublishedProject', on_delete=models.CASCADE, null=True, blank=True, related_name='experimental_annotations')
    target_project_version = models.CharField(max_length=15, default='', blank=True)
    target_filepath = models.CharField(max_length=500, help_text="Path to the target file being annotated")
    target_modality = models.CharField(
        max_length=32, 
        choices=[
            ("image", "image"),
            ("document", "document"),
        ],
        db_index=True
    )
    annotation_description = models.TextField(blank=True) #description of what annotations mean
    
    created_by = models.ForeignKey('user.User', on_delete=models.CASCADE, related_name='experimental_annotations')
    created_datetime = models.DateTimeField(auto_now_add=True)
    updated_datetime = models.DateTimeField(auto_now=True)
    
    class Meta:
        default_permissions = ('add', 'delete', 'change')


class AnnotationData(models.Model):
    """
    Example: 
    {"label_texts": ["Test Data", "Test Data 2"]} or 
    {"bounding_boxes": [{"x": 10, "y": 10, "width": 100, "height": 100}]}
    """
    annotation = models.ForeignKey(Annotation, on_delete=models.CASCADE, related_name='annotation_data')
    label_texts = models.JSONField(default=list) # list of label strings

### Defining the Types of Annotation Data
class DocumentAnnotationData(AnnotationData):
    target_text = models.TextField(blank=True)


@receiver(post_save, sender=Annotation)
def create_annotation_data(sender, **kwargs):
    """
    Automatically creates appropriate AnnotationData when an Annotation is created.
    """
    annotation = kwargs['instance']
    if kwargs['created']:  # Only run when a new annotation is created
        if annotation.target_modality == 'document':
            DocumentAnnotationData.objects.create(annotation=annotation)
        # Add other modalities here as needed
        # elif annotation.target_modality == 'image':
        #     ImageAnnotationData.objects.create(annotation=annotation)