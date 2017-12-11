from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from ckeditor.fields import RichTextField

from user.models import BaseAffiliation


class Project(models.Model):
    """
    The core project model to be inherited by different project types

    This model should contain some fields which help map
    projects to datacite:
    https://schema.datacite.org/
    https://schema.datacite.org/meta/kernel-4.0/doc/DataCite-MetadataKernel_v4.0.pdf
    """
    # Content description

    # The title should be changeable for the project...
    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=20, unique=True, null=True)
    abstract = RichTextField(max_length=10000)
    background = RichTextField()
    methods = RichTextField()
    acknowledgements = RichTextField()
    paper_citations = models.ManyToManyField('project.Reference', related_name='%(class)s_citations')
    references = models.ManyToManyField('project.Reference', related_name='%(class)s_references')
    topics = models.ManyToManyField('project.Topic', related_name='%(class)s')

    # Access policy 
    dua = models.ForeignKey('project.DUA', null=True, blank=True, related_name='%(class)s')
    training_course = models.ForeignKey('project.TrainingCourse', null=True, blank=True, related_name='%(class)s')
    id_verification_required = models.BooleanField(default=False)

    # Back-end information 
    creation_date = models.DateTimeField(auto_now_add=True)
    # Maximum allowed storage capacity in GB
    storage_allowance = models.SmallIntegerField(default=10)
    owner = models.ForeignKey('user.User', related_name='owned_%(class)s')
    collaborators = models.ManyToManyField('user.User', related_name='collaborating_%(class)s')
    editor = models.ForeignKey('user.User', related_name='editing_%(class)s', null=True)
    reviewers = models.ManyToManyField('user.User', related_name='reviewing_%(class)s')
    # 0=prepublish, 1=under review (unable to edit), 2=published static,
    # Core projects cycles back and forth between 0-1 until editor agrees to
    # publish.
    status = models.SmallIntegerField(default=0)

    # Information for published projects
    #core_project = models.ForeignKey('project.Project', related_name='releases', blank=True, null=True)
    # Changes from previous version (if any)
    changelog = RichTextField()
    # Total file storage size in bytes
    storage_size = models.IntegerField(null=True)
    publish_date = models.DateField(null=True)
    version_number = models.FloatField(null=True)
    is_final_version = models.BooleanField(default=False)
    doi = models.CharField(max_length=50, default='')

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    def __unique__(self):
        # There is only a need to check uniqueness among non-published projects
        if self.is_published:
            return True



        #if self.title not in set([title for d.title in DataBase.objects.all()])


class Database(Project):
    """
    A database project
    """
    technical_validation = RichTextField()
    data_description = RichTextField()
    usage_notes = RichTextField()


class SoftwarePackage(Project):
    """
    A software project
    """
    technical_validation = RichTextField()
    usage_notes = RichTextField()


class Tutorial(Project):
    """
    A tutorial project
    """
    pass


class Challenge(Project):
    """
    A challenge project
    """
    submission_deadline = models.DateTimeField()


# class Review(models.Model):
#     """
#     Project review
#     """
#     project = models.ForeignKey('project.Project', related_name='reviews')
#     submission_date = models.DateTimeField(null=True)


# class StorageRequest(models.Model):
#     """
#     A request for storage capacity for a project
#     """
#     # Requested storage size in GB
#     storage_size = models.SmallIntegerField()
#     project = models.OneToOneField('project.Project')
#     request_date = models.DateTimeField(auto_now_add=True)


class AuthorInfo(models.Model):
    """
    Data owners/authors. Credited for contributing/owning the data
    
    Static snapshot/manually entered info, rather than info
    being based on profile fields liable to change.
    """
    # The project_object points to one of the project models.
    # Do not confuse this built in content_type variable with project resource type.
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project_object = GenericForeignKey('content_type', 'object_id')

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
    """
    author_info = models.ForeignKey('project.AuthorInfo', related_name='affiliations')


class Topic(models.Model):
    """
    Topic information to tag projects
    """
    description = models.CharField(max_length=50)


class Reference(models.Model):
    title = models.CharField(max_length=100)
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

