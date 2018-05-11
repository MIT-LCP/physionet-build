import os
import shutil

from ckeditor.fields import RichTextField
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.template.defaultfilters import slugify

from .utility import get_tree_size

import pdb

# Size limit for individual files being uploaded to projects
PROJECT_FILE_SIZE_LIMIT = 100 * 1024**2

def new_creation(receiver_function):
    """
    Decorator for a receiver function to only trigger upon model
    creation from non-fixtures.
    """
    def func_wrapper(*args, **kwargs):
        if kwargs.get('created') and not kwargs.get('raw'):
            return receiver_function(*args, **kwargs)

    return func_wrapper


class AffiliationManager(models.Manager):
    def get_by_natural_key(self, author_email, project, name):
        return self.get(member_object__email=author_email, project=project,
            name=name)

class Affiliation(models.Model):
    """
    Affiliations belonging to an author or collaborator

    """
    objects = AffiliationManager()

    name = models.CharField(max_length=255)
    # member_object points to a Creator or Contributor.
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    member_object = GenericForeignKey('content_type', 'object_id')

    def natural_key(self):
        return self.member_object.natural_key() + (self.name,)
    natural_key.dependencies = ['project.Author']

    class Meta:
        unique_together = (('name', 'content_type', 'object_id'))


class Member(models.Model):
    """
    Inherited by the Author and Contributor classes.

    """
    # The member will point to a project OR published project
    project = models.ForeignKey('project.Project', related_name='%(class)ss',
        null=True, blank=True)
    published_project =models.ForeignKey('project.PublishedProject',
        related_name='%(class)s', null=True, blank=True)

    first_name = models.CharField(max_length=100, default='')
    middle_names = models.CharField(max_length=200, default='', blank=True)
    last_name = models.CharField(max_length=100, default='')
    is_human = models.BooleanField(default=True)
    organization_name = models.CharField(max_length=200, default='')
    display_order = models.PositiveSmallIntegerField()
    affiliations = GenericRelation(Affiliation)

    def __str__(self):
        if self.is_human:
            return self.user.__str__()
        else:
            return self.organization_name

    class Meta:
        abstract = True

    def get_full_name(self):
        if self.middle_names:
            return ' '.join([self.first_name, self.middle_names,
                           self.last_name])
        else:
            return ' '.join([self.first_name, self.last_name])


class AuthorManager(models.Manager):
    def get_by_natural_key(self, user_email, project):
        return self.get(user__email=user_email, project=project)


class Author(Member):
    """
    A project's author/creator (datacite). Credited for creating the
    resource.

    Datacite definition:
        "The main researchers involved
        in producing the data, or the
        authors of the publication, in
        priority order."

    """
    class Meta:
        unique_together = (('user', 'project'), ('user', 'published_project'),)

    def natural_key(self):
        return self.user.natural_key() + (self.project,)
    natural_key.dependencies = ['user.User', 'project.Project']

    objects = AuthorManager()

    # Authors must have physionet profiles, unless they are organizations.
    user = models.ForeignKey('user.User', related_name='authorships',
        blank=True, null=True)

@receiver(post_save, sender=Author)
@new_creation
def setup_author(sender, **kwargs):
    """
    When an Author is created:
    - Import profile names.
    """
    author = kwargs['instance']
    if author.is_human:
        profile = author.user.profile
        for field in ['first_name', 'middle_names', 'last_name']:
            setattr(author, field, getattr(profile, field))
        author.save()


class Contributor(Member):
    """
    A resource contributor.

    Datacite definition:
        "The institution or person
        responsible for collecting,
        managing, distributing, or
        otherwise contributing to the
        development of the resource."

    """
    contributor_type_choices = (
        ('ContactPerson', 'Contact Person'),
        ('DataCollector', 'Data Collector'),
        ('DataCurator', 'Data Curator'),
        ('DataManager', 'Data Manager'),
        ('Distributor', 'Distributor'),
        ('Editor', 'Editor'),
        ('HostingInstitution', 'Hosting Institution'),
        ('Producer', 'Producer'),
        ('ProjectLeader', 'Project Leader'),
        ('ProjectManager', 'Project Manager'),
        ('ProjectMember', 'Project Member'),
        ('RegistrationAgency', 'Registration Agency'),
        ('RegistrationAuthority', 'Registration Authority'),
        ('RelatedPerson', 'Related Person'),
        ('Researcher', 'Researcher'),
        ('ResearchGroup', 'Research Group'),
        ('RightsHolder', 'Rights Holder'),
        ('Sponsor', 'Sponsor'),
        ('Supervisor', 'Supervisor'),
        ('WorkPackageLeader', 'Work Package Leader'),
        ('Other', 'Other'),
    )

    contributor_type = models.CharField(max_length=20,
        choices=contributor_type_choices)


class Topic(models.Model):
    """
    Topic information to tag projects
    """
    description = models.CharField(max_length=50)
    project = models.ForeignKey('project.Project', related_name='topics')

    def __str__(self):
        return self.description


class PublishedTopic(models.Model):
    """
    Topic information to tag published projects
    """
    description = models.CharField(max_length=50)

    def __str__(self):
        return self.description


class Reference(models.Model):
    """
    General reference field for projects
    """
    description = models.CharField(max_length=250)
    order = models.PositiveSmallIntegerField()

    # Project or PublishedProject
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        unique_together = (('order', 'content_type', 'object_id'))


class Metadata(models.Model):
    """
    Metadata for all projects.

    https://schema.datacite.org/
    https://schema.datacite.org/meta/kernel-4.0/doc/DataCite-MetadataKernel_v4.1.pdf
    https://www.nature.com/sdata/publish/for-authors#format

    """
    class Meta:
        abstract = True

    resource_types = (
        ('Database', 'Database'),
        ('Software', 'Software'),
    )

    access_policies = (
        ('Open', 'Open'),
        ('Disclaimer', 'Disclaimer'),
        ('Protected', 'Protected'),
    )

    # Main body descriptive metadata

    resource_type = models.CharField(max_length=10, choices=resource_types)
    title = models.CharField(max_length=200)
    # datacite: "A brief description of the resource and the context in
    # which the resource was created"
    abstract = RichTextField(max_length=10000, blank=True)
    background = RichTextField(blank=True)
    methods = RichTextField(blank=True)
    content_description = RichTextField(blank=True)
    technical_validation = RichTextField(blank=True)
    usage_notes = RichTextField(blank=True)
    acknowledgements = RichTextField(blank=True)
    references = GenericRelation(Reference, blank=True)

    # Supplementary descriptive fields

    # External home page
    project_home_page = models.URLField(default='', blank=True)
    # The additional papers to cite when citing the database
    project_citations =GenericRelation(Reference, blank=True)
    topics = GenericRelation(Topic, blank=True)
    version = models.CharField(max_length=15, default='', blank=True)
    changelog_summary = RichTextField(blank=True)
    access_policy = models.CharField(max_length=10, choices=access_policies,
                                     default=access_policies[0][0])


class Project(Metadata):
    """
    The model for user-owned projects.
    """
    creation_datetime = models.DateTimeField(auto_now_add=True)
    modified_datetime = models.DateTimeField(auto_now=True)

    # Maximum allowed storage capacity in GB
    storage_allowance = models.SmallIntegerField(default=1)
    submitting_author = models.ForeignKey('user.User',
        related_name='submitting_projects')

    published = models.BooleanField(default=False)
    under_review = models.BooleanField(default=False)

    class Meta:
        unique_together = (('title', 'submitting_author', 'resource_type'),)

    def __str__(self):
        return self.title

    def file_root(self):
        "Root directory containing the project's files"
        return os.path.join(settings.MEDIA_ROOT, 'projects', str(self.id))

    def storage_used(self):
        "Total storage used in bytes"
        return get_tree_size(self.file_root())

    def is_publishable(self):
        """
        Whether the project can be published
        """
        return True

    def publish(self):
        """
        Create a published version of this project
        """
        if not self.is_publishable:
            raise Exception('Nope')

        published_project = PublishedProject()

        # Direct copy over fields
        for attr in ['title', 'abstract', 'background', 'methods',
                     'content_description', 'technical_validation',
                     'usage_notes', 'acknowledgements']:
            setattr(pulished_project, attr, getattr(self, attr))

        # New content
        published_project.core_project = self
        published_project.storage_size = self.storage_used()
        # To be implemented...
        published_project.doi = '10.13026/C2F305'

        published_project.save()


        # Same content, different objects, requiring the new object
        # to be saved
        for reference in self.references.all():
            reference_copy = Reference.objects.create(
                description=reference.description, order=description.order,
                project_object=published_project)
            reference_copy.save()

        for topic in self.topics.all():
            published_topic = PublishedTopic.objects.filter(description=topic.description.lower())
            # If same content object exists, add it. Otherwise create.
            if published_topic.count():
                published_project.topics.add(published_topic.first())
            else:
                published_topic = PublishedTopic.objects.create(description=topic.description.lower())
                published_project.topics.add(published_topic)


@receiver(post_save, sender=Project)
@new_creation
def setup_project(sender, **kwargs):
    """
    When a Project is created:
    - create an Author object from the submitting_author field
    - create the project file directory
    """
    project = kwargs['instance']
    user = project.submitting_author
    Author.objects.create(project=project, user=user, display_order=1)
    # Create file directory
    os.mkdir(project.file_root())

@receiver(pre_delete, sender=Project)
def cleanup_project(sender, **kwargs):
    """
    Before a Project is deleted:
    - delete the project file directory
    """
    project = kwargs['instance']

    # Delete file directory
    project_root = project.file_root()
    if os.path.islink(project_root):
        os.unlink(project_root)
    elif os.path.isdir(project_root):
        shutil.rmtree(project_root)

class PublishedProject(Metadata):
    """
    A published project. Immutable snapshot.

    """
    slug = models.SlugField(max_length=30)
    # The Project this object was created from
    core_project = models.ForeignKey('project.Project',
        related_name='published_project', blank=True, null=True)
    topics = models.ManyToManyField('project.PublishedTopic',
                                    related_name='tagged_projects')
    # Total file storage size in bytes
    storage_size = models.IntegerField()
    publish_datetime = models.DateTimeField()
    is_newest_version = models.BooleanField(default=True)
    doi = models.CharField(max_length=50, default='', unique=True)

    class Meta:
        unique_together = (('title', 'version'),)


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
    user = models.ForeignKey('user.User',
        related_name='training_course_completions')
    date = models.DateField(auto_now_add=True)
    training_course = models.ForeignKey('project.TrainingCourse',
        related_name='training_course_completions')


class BaseInvitation(models.Model):
    """
    Base class for project invitations and storage requests
    """
    request_datetime = models.DateTimeField(auto_now_add=True)
    response_datetime = models.DateTimeField(null=True)
    response = models.NullBooleanField(null=True)
    response_message = models.CharField(max_length=50, default='', blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True

class Invitation(BaseInvitation):
    """
    Invitation to join a project as an, author, or reviewer

    """
    project = models.ForeignKey('project.Project',
        related_name='invitations')
    # The target email
    email = models.EmailField(max_length=255)
    # User who made the invitation
    inviter = models.ForeignKey('user.User')
    # Either 'author', or 'reviewer'
    invitation_type = models.CharField(max_length=10)


    def __str__(self):
        return ('Project: %s To: %s By: %s'
                % (self.project, self.email, self.inviter))

    def get_user_invitations(user, invitation_types='all',
                             exclude_duplicates=True):
        """
        Get all active invitations to a user

        """
        emails = user.get_emails()
        invitations = Invitation.objects.filter(email__in=emails,
            is_active=True).order_by('-request_datetime')
        if invitation_types != 'all':
            invitations = invitations.filter(
                invitation_type__in=invitation_types)

        # Remove duplicate invitations to the same project
        if exclude_duplicates:
            project_ids = []
            remove_ids = []
            for invitation in invitations:
                if invitation.project.id in project_ids:
                    remove_ids.append(invitation.id)
                else:
                    project_ids.append(invitation.project.id)
            invitations = invitations.exclude(id__in=remove_ids)

        return invitations

    def is_invited(user, project, invitation_types='all'):
        "Whether a user is invited to a project"
        user_invitations = get_user_invitations(user=user,
            invitation_types=invitation_types)

        return bool(project in [inv.project for inv in invitations])


class StorageRequest(BaseInvitation):
    """
    A request for storage capacity for a project
    """
    project = models.ForeignKey('project.Project', related_name='storage_requests')
    # Requested storage size in GB
    request_allowance = models.SmallIntegerField(
        validators=[MaxValueValidator(100), MinValueValidator(1)])

    # The authorizer
    responder = models.ForeignKey('user.User', null=True)


class Review(models.Model):
    """
    Project review
    """
    project = models.ForeignKey('project.Project', related_name='reviews')
    start_date = models.DateTimeField(auto_now_add=True)
    submission_date = models.DateTimeField(null=True)
    editor = models.ForeignKey('user.User', related_name='edits', null=True)
    reviewers = models.ManyToManyField('user.User', related_name='reviews')
