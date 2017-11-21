from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from ckeditor.fields import RichTextField

from user.models import BaseAffiliation


class Project(models.Model):
    """
    The model for the core variable projects.
    The descriptive information is stored in its `project_metadata` target.
    """
    creation_date = models.DateTimeField(auto_now_add=True)
    # Maximum allowed storage capacity in GB
    storage_allowance = models.SmallIntegerField(default=10)
    owner = models.ForeignKey('user.User', related_name='owned_%(class)s')
    collaborators = models.ManyToManyField('user.User', related_name='collaborating_%(class)s')
    
    # 0=prepublish, 1=under review (unable to edit), 2=published
    # Projects cycle between 0-1 or 2-1 until editor agrees to publish.
    status = models.SmallIntegerField(default=0)

    # The type of resource: data, software, tutorial, challenge
    resource_type = models.ForeignKey('project.ResourceType')
    
    # Generic foreign key to the information for the project type. Allowed
    # models should be DatabaseMetadata, SoftwareMetaData
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project_metadata = GenericForeignKey('content_type', 'object_id')

    def validate_unique(self, *args, **kwargs):
        super(Project, self).validate_unique(*args, **kwargs)
        # The same owner cannot have multiple projects with the same name
        owner_projects = Project.objects.filter(owner=self.owner)
        if owner_projects.filter(project_metadata__title=self.project_metadata__title):
            raise ValidationError('You may not own multiple projects with the same name')

        # qs = Room.objects.filter(name=self.name)
        # if qs.filter(zone__site=self.zone__site).exists():
        #     raise ValidationError({'name':['Name must be unique per site',]})


class ResourceType(models.Model):
    """
    A type of resource: data, software, tutorial, challenge
    """
    description = models.CharField(max_length=20)


class PublishedProjectInfo(models.Model):
    """
    Fields common to all published projects, that are also not relevant to the
    core variable Project
    """
    # The Project object this object was created from
    core_project = models.ForeignKey('project.Project', related_name='published_%(class)s', blank=True, null=True)
    # Total file storage size in bytes
    storage_size = models.IntegerField(null=True)
    publish_date = models.DateField(null=True)
    is_final_version = models.BooleanField(default=False)
    doi = models.CharField(max_length=50, default='')

    class Meta:
        abstract = True
        unique_together = (('title', 'version_number'),)


class ProjectMetadata(models.Model):
    """
    Common metadata for all types of projects. Inherited by  published project
    classes, and project metadata classes, of all resource types.
    """
    class Meta:
        abstract = True

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=30)
    abstract = RichTextField(max_length=10000)
    
    acknowledgements = RichTextField()
    paper_citations = models.ManyToManyField('project.Reference', related_name='%(class)s_citations')
    references = models.ManyToManyField('project.Reference', related_name='%(class)s_references')
    topics = models.ManyToManyField('project.Topic', related_name='%(class)s')

    # Access policy
    # Consideration: What happens when dua/training course objects change?
    dua = models.ForeignKey('project.DUA', null=True, blank=True, related_name='%(class)s')
    training_course = models.ForeignKey('project.TrainingCourse', null=True, blank=True, related_name='%(class)s')
    id_verification_required = models.BooleanField(default=False)

    # Version and changes (if any)
    version_number = models.FloatField(null=True)
    changelog = RichTextField()


class DatabaseMetadata(ProjectMetadata):
    """
    Model containing information for database projects.
    - Linked to Project.
    - Fields inherited by Database.

    This model (including inherited fields) should contain some fields which
    help map projects to datacite:
    https://schema.datacite.org/
    https://schema.datacite.org/meta/kernel-4.0/doc/DataCite-MetadataKernel_v4.0.pdf
    """
    background = RichTextField()
    methods = RichTextField()
    technical_validation = RichTextField()
    data_description = RichTextField()
    usage_notes = RichTextField()


class SoftwareMetadata(ProjectMetadata):
    """
    Model containing information for software projects.
    - Linked to Project.
    - Fields inherited by SoftwarePackage.
    """
    technical_validation = RichTextField()
    usage_notes = RichTextField()


class Database(DatabaseMetadata, PublishedProjectInfo):
    """
    A published database. The first resource type.
    """
    pass


class SoftwarePackage(SoftwareMetadata, PublishedProjectInfo):
    """
    A published software package. The second resource type.
    """
    pass


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
    # Requested storage size in GB
    storage_size = models.SmallIntegerField()
    project = models.OneToOneField('project.Project')
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

    order = models.SmallIntegerField(default=0)


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

