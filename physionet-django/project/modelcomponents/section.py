from html import unescape

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils.html import strip_tags

from project.models import SafeHTMLField


class ProjectSection(models.Model):
    """
    The content sections for each ProjectType
    """
    title = models.CharField(max_length=30)
    html_id = models.SlugField(max_length=30)
    description = models.TextField()
    resource_type = models.ForeignKey(
        'project.ProjectType', db_column='resource_type',
        related_name='%(class)ss', on_delete=models.PROTECT)
    default_order = models.PositiveSmallIntegerField()
    required = models.BooleanField()

    class Meta:
        unique_together = (('resource_type', 'title'),
            ('resource_type', 'default_order'),
            (('resource_type', 'html_id')))


class SectionContent(models.Model):
    """
    The content for each section of a project
    """
    project_section = models.ForeignKey(
        'project.ProjectSection', db_column='project_section',
        related_name='%(class)ss', on_delete=models.PROTECT,
        null=True)

    custom_title = models.CharField(max_length=30, null=True)
    custom_order = models.PositiveSmallIntegerField(null=True)
    section_content = SafeHTMLField(blank=True)

    class Meta:
        abstract = True
        unique_together = (('project', 'project_section'),)

    def is_valid(self):
        text = unescape(strip_tags(self.section_content))
        return text and not text.isspace()


class PublishedSectionContent(SectionContent):
    project = models.ForeignKey('project.PublishedProject',
        related_name='project_content', on_delete=models.CASCADE)


class ActiveSectionContent(SectionContent):
    project = models.ForeignKey('project.ActiveProject',
        related_name='project_content', on_delete=models.CASCADE)


class ArchivedSectionContent(SectionContent):
    project = models.ForeignKey('project.ArchivedProject',
        related_name='project_content', on_delete=models.CASCADE)
