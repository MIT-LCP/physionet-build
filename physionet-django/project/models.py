from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.defaultfilters import slugify
import os

from ckeditor.fields import RichTextField

from physionet.settings import MEDIA_ROOT
from user.models import BaseAffiliation
from .utility import get_tree_size


class CommonMetadata(models.Model):
    """
    Common metadata for all types of projects. Inherited by published project
    classes, and project metadata classes, of all resource types.
    """
    class Meta:
        abstract = True

    title = models.CharField(max_length=200)
    abstract = RichTextField(max_length=10000, blank=True)
    
    acknowledgements = RichTextField(blank=True)
    paper_citations = models.ManyToManyField('project.Reference', related_name='%(class)s_citations', blank=True)
    references = models.ManyToManyField('project.Reference', related_name='%(class)s_references', blank=True)
    topics = models.ManyToManyField('project.Topic', related_name='%(class)s', blank=True)

    # Access policy
    # Consideration: What happens when dua/training course objects change?
    dua = models.ForeignKey('project.DUA', null=True, blank=True, related_name='%(class)s')
    training_course = models.ForeignKey('project.TrainingCourse', null=True, blank=True, related_name='%(class)s')
    id_verification_required = models.BooleanField(default=False)

    # Version and changes (if any)
    version_number = models.FloatField(null=True, blank=True)
    changelog = RichTextField(blank=True)


class DatabaseMetadata(models.Model):
    """
    Metadata fields only possessed by databases

    This model (including inherited fields) should contain some fields which
    help map projects to datacite:
    https://schema.datacite.org/
    https://schema.datacite.org/meta/kernel-4.0/doc/DataCite-MetadataKernel_v4.0.pdf
    """
    class Meta:
        abstract = True

    background = RichTextField(blank=True)
    methods = RichTextField(blank=True)
    data_description = RichTextField(blank=True)


class SoftwareMetadata(models.Model):
    """
    Metadata fields only possessed by software packages
    """
    class Meta:
        abstract = True

    technical_validation = RichTextField(blank=True)
    usage_notes = RichTextField(blank=True)
    source_controlled_location = models.URLField(blank=True)


class Project(CommonMetadata, DatabaseMetadata, SoftwareMetadata):
    """
    The model for user-owned projects.
    """
    # The type of resource: data, software, tutorial, challenge
    resource_type = models.ForeignKey('project.ResourceType')

    creation_datetime = models.DateTimeField(auto_now_add=True)
    modified_datetime = models.DateTimeField(auto_now=True)

    # Maximum allowed storage capacity in GB
    storage_allowance = models.SmallIntegerField(default=2)
    owner = models.ForeignKey('user.User', related_name='owned_projects')
    collaborators = models.ManyToManyField('user.User', related_name='collaborating_projects')
    
    published = models.BooleanField(default=False)
    under_review = models.BooleanField(default=False)

    class Meta:
        unique_together = (('title', 'owner'),)

    def __str__(self):
        return self.title

    def file_root(self):
        "Root directory containing the project's files"
        return os.path.join(MEDIA_ROOT, 'projects', str(self.id))

    def storage_used(self):
        "Total storage used in bytes"
        return get_tree_size(self.file_root())


class ResourceTypeManager(models.Manager):
    "Manager class for ResourceType"
    def get_by_natural_key(self, description):
        return self.get(description=description)


class ResourceType(models.Model):
    """
    A type of resource: data, software, tutorial, challenge
    """
    description = models.CharField(max_length=20)

    objects = ResourceTypeManager()

    def __str__(self):
        return self.description

    def natural_key(self):
        return (self.description,)


class PublishedProject(models.Model):
    """
    Fields common to all published projects, that are also not relevant to the
    core variable Project
    """
    slug = models.SlugField(max_length=30)
    # The Project this object was created from
    core_project = models.ForeignKey('project.Project', related_name='published_%(class)s', blank=True, null=True)
    # Total file storage size in bytes
    storage_size = models.IntegerField(null=True)
    publish_date = models.DateField(null=True)
    is_final_version = models.BooleanField(default=False)
    doi = models.CharField(max_length=50, default='')

    class Meta:
        abstract = True
        unique_together = (('title', 'version_number'),)


class Database(CommonMetadata, DatabaseMetadata, PublishedProject):
    """
    A published database
    """
    title = models.CharField(max_length=200, unique=True)


class SoftwarePackage(CommonMetadata, SoftwareMetadata, PublishedProject):
    """
    A published software package
    """
    title = models.CharField(max_length=200, unique=True)


class Review(models.Model):
    """
    Project review
    """
    project = models.ForeignKey('project.Project', related_name='reviews')
    start_date = models.DateTimeField(auto_now_add=True)
    submission_date = models.DateTimeField(null=True)
    editor = models.ForeignKey('user.User', related_name='edits', null=True)
    reviewers = models.ManyToManyField('user.User', related_name='reviews')


class StorageRequest(models.Model):
    """
    A request for storage capacity for a project
    """
    project = models.OneToOneField('project.Project')
    # Requested storage size in GB
    storage_size = models.SmallIntegerField()
    request_date = models.DateTimeField(auto_now_add=True)


class AuthorInfo(models.Model):
    """
    Data owner/author. Credited for contributing/owning the data
    
    Static snapshot/manually entered info, rather than info
    being based on profile fields liable to change.
    """
    # The project_object points to one of the project models.
    # Do not confuse this built in content_type variable with project resource type.
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    published_project = GenericForeignKey('content_type', 'object_id')

    author = models.ForeignKey('user.User', related_name='author_info')
    is_submitting_author = models.BooleanField(default=False)
    equal_contributor = models.BooleanField(default=False)
    display_order = models.SmallIntegerField()
    
    first_name = models.CharField(max_length=100)
    middle_names = models.CharField(max_length=200)
    last_name = models.CharField(max_length=100)


class AffiliationInfo(BaseAffiliation):
    """
    Author affiliation snapshot upon project publication.
    An author may have multiple affiliations
    """
    author_info = models.ForeignKey('project.AuthorInfo', related_name='affiliations')
    

class Topic(models.Model):
    """
    Topic information to tag projects
    """
    description = models.CharField(max_length=50)

    def __str__(self):
        return self.description


class Reference(models.Model):
    """
    General reference link and description
    """
    description = models.CharField(max_length=100)
    url = models.URLField()


class DUA(models.Model):
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=20, null=True)
    description = RichTextField()
    content = RichTextField()


class TrainingCourse(models.Model):
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=20, null=True)
    description = RichTextField()
    url = models.URLField()


class DUASignature(models.Model):
    user = models.ForeignKey('user.User', related_name='dua_signatures')
    date = models.DateField(auto_now_add=True)
    dua = models.ForeignKey('project.DUA', related_name='dua_signatures')


class TrainingCourseCompletion(models.Model):
    user = models.ForeignKey('user.User', related_name='training_course_completions')
    date = models.DateField(auto_now_add=True)
    training_course = models.ForeignKey('project.TrainingCourse', related_name='training_course_completions')
