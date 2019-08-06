from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey

from project.models import SafeHTMLField


class ProjectSection(models.Model):
    """
    The content sections for each ProjectType
    """
    name = models.CharField(max_length=30)
    description = models.TextField()
    resource_type = models.ForeignKey('project.ProjectType',
                                    db_column='resource_type',
                                    related_name='%(class)ss',
                                    on_delete=models.PROTECT)
    default_order = models.PositiveSmallIntegerField()
    required = models.BooleanField()

    class Meta:
        unique_together = (('name', 'resource_type'),)
        unique_together = (('resource_type', 'default_order'),)


class SectionContent(models.Model):
    """
    The content for each section of a project
    """
    content_type = models.ForeignKey(models.ContentType,
                                     on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    project_section = models.ForeignKey('project.ProjectSection',
                                    db_column='project_section',
                                    related_name='%(class)ss',
                                    on_delete=models.PROTECT)
    section_content = SafeHTMLField(blank=True)

    class Meta:
        unique_together = (('content_type', 'object_id', 'project_section'),)

