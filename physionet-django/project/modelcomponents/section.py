from django.db import models

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
                                    on_delete=models.CASCADE)
    default_order = models.PositiveSmallIntegerField()
    required = models.BooleanField()

    class Meta:
        unique_together = (('name', 'resource_type'),)
        unique_together = (('resource_type', 'default_order'),)


class SectionContent(models.Model):
    """
    The content for each section of a project
    """
    project_id = models.ForeignKey('project.CoreProject',
                                    db_column='project_id',
                                    related_name='%(class)ss',
                                    on_delete=models.CASCADE)
    project_section = models.ForeignKey('project.ProjectSection',
                                    db_column='project_section',
                                    related_name='%(class)ss',
                                    on_delete=models.CASCADE)
    content = SafeHTMLField(blank=True)

    class Meta:
        unique_together = (('project_id', 'project_section'),)

