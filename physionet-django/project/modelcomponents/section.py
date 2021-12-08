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
        unique_together = (
            ('resource_type', 'title'),
            ('resource_type', 'default_order'),
            (('resource_type', 'html_id'))
        )


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

    @classmethod
    def from_db(cls, *args, **kwargs):
        """
        Instantiate an object from the database.
        """
        instance = super(SectionContent, cls).from_db(*args, **kwargs)

        # Save the original field values so that we can later check if
        # they have been modified.  Note that by using __dict__, this
        # will omit any deferred fields.
        instance.orig_content = instance.section_content
        return instance

    def save(self, *, content_modified=None,
             force_insert=False, update_fields=None, **kwargs):

        # Use default behaviour if not dealing with UnpublishedProject
        from project.models import UnpublishedProject
        if not isinstance(self.project, UnpublishedProject):
            return super().save(force_insert=force_insert,
                                update_fields=update_fields,
                                **kwargs)

        # Note: UnpublishedProject.modified_datetime is an auto_now field,
        # so it is automatically set to the current time (unless we exclude it
        # using update_fields.)

        if force_insert or update_fields:
            # If force_insert is specified, then we want to insert a
            # new object, which means setting the timestamp.  If
            # update_fields is specified, then we want to update
            # precisely those fields.  In either case, use the default
            # save method.
            content_modified = True

        if hasattr(self, 'orig_content'):
            # Check whether any of the Metadata fields have been
            # modified since the object was loaded from the database.
            if self.orig_content != self.section_content:
                content_modified = True
        else:
            # If the object was not initially created by from_db,
            # assume content has been modified.
            content_modified = True

        if content_modified:
            # If content has been modified, then save normally.
            self.project.save(update_fields=["modified_datetime"])
        return super().save(force_insert=force_insert,
                            update_fields=update_fields,
                            **kwargs)


class PublishedSectionContent(SectionContent):
    project = models.ForeignKey(
        'project.PublishedProject',
        related_name='project_contents', on_delete=models.CASCADE)


class ActiveSectionContent(SectionContent):
    project = models.ForeignKey(
        'project.ActiveProject',
        related_name='project_contents', on_delete=models.CASCADE)


class ArchivedSectionContent(SectionContent):
    project = models.ForeignKey(
        'project.ArchivedProject',
        related_name='project_contents', on_delete=models.CASCADE)
