from django.db import models
from ckeditor.fields import RichTextField
from user.models import Affiliation


class Project(models.Model):
    """
    The core project model

    This model should contain some fields which help map
    projects to datacite:
    https://schema.datacite.org/
    https://schema.datacite.org/meta/kernel-4.0/doc/DataCite-MetadataKernel_v4.0.pdf
    """
    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=20, unique=True)

    # 0=pre-submission, 1=under review, 2=published, 
    status = models.SmallIntegerField(default=0)

    # Access control
    owner = models.ForeignKey('user.User', related_name='owned_project') 

    # The top reviewer who authorizes/manages the review.
    editor = models.ForeignKey('user.User', related_name='editing_project', null=True)
    # People reviewing the project for publication
    reviewers = models.ManyToManyField('user.User', related_name='reviewing_project')

    # Access policy
    dua = models.ForeignKey('project.DUA', null=True, blank=True, related_name='project')
    training_course = models.ForeignKey('project.TrainingCourse', null=True, blank=True, related_name='project')
    id_verification = models.BooleanField(default=False)

    # Project metadata
    doi = models.CharField(max_length=50, default='')
    resource_type = models.ForeignKey('project.ResourceType', null=True)

    topics = models.ManyToManyField('project.Topic')
    # Size of all files. Only calculated/stored once upon publication
    size = models.IntegerField(null=True)

    # Project description
    abstract = RichTextField(max_length=1000)
    background = RichTextField()
    methods = RichTextField()
    data_description = RichTextField()
    technical_validation = RichTextField()
    usage_notes = RichTextField()
    acknowledgements = RichTextField()
    paper_citations = models.ManyToManyField('project.Reference', related_name='project_paper_citation')
    references = models.ManyToManyField('project.Reference', 'project_reference')

    def __str__(self):
        return self.title


class AuthorInfo(Affiliation):
    """
    Data owners/authors. Credited for contributing/owning the data
    
    Static snapshot/manually entered info, rather than info
    being based on profile fields liable to change.
    """
    project = models.ForeignKey('project.Project', related_name='author_info')

    author = models.ForeignKey('user.User', related_name='author_info')
    is_submitting_author = models.BooleanField(default=False)
    equal_contributor = models.BooleanField(default=False)
    display_order = models.SmallIntegerField()
    
    first_name = models.CharField(max_length=100)
    middle_names = models.CharField(max_length=200)
    last_name = models.CharField(max_length=100)


class ResourceType(models.Model):
    """
    The general resource class of the project
    eg. data, software, tutorial
    """
    description = models.CharField(max_length=50)


class Topic(models.Model):
    """
    Topic information to tag projects
    """
    description = models.CharField(max_length=50)


class Reference(models.Model):
    title= models.CharField(max_length=100)


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
    user = models.ForeignKey('user.User', related_name='dua_signature')
    date = models.DateField(auto_now_add=True)
    dua = models.ForeignKey('project.DUA', related_name='dua_signature')


class TrainingCourseCompletion(models.Model):
    user = models.ForeignKey('user.User', related_name='training_course_completion')
    date = models.DateField(auto_now_add=True)
    training_course = models.ForeignKey('project.TrainingCourse', related_name='training_course_completion')

