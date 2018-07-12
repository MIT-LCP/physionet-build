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
from django.utils import timezone

from user.models import User
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
        related_name='%(class)ss', null=True, blank=True)

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
    if author.is_human and author.user:
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
    General reference field for projects, for the descriptive metadata
    """
    description = models.CharField(max_length=250)
    # Project or PublishedProject
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        unique_together = (('description', 'content_type', 'object_id'),)

    def __str__(self):
        return self.description


class Contact(models.Model):
    name = models.CharField(max_length=120)
    affiliation = models.CharField(max_length=100)
    email = models.EmailField(max_length=255)

    # Project or PublishedProject
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project_object = GenericForeignKey('content_type', 'object_id')


class Publication(models.Model):
    """
    The related publications for a project.
    """
    citation = models.CharField(max_length=250)
    url = models.URLField()

    # Project or PublishedProject
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project_object = GenericForeignKey('content_type', 'object_id')


class Metadata(models.Model):
    """
    Metadata for Projects and PublishedProjects.

    https://schema.datacite.org/
    https://schema.datacite.org/meta/kernel-4.0/doc/DataCite-MetadataKernel_v4.1.pdf
    https://www.nature.com/sdata/publish/for-authors#format

    """
    class Meta:
        abstract = True

    resource_types = (
        (0, 'Database'),
        (1, 'Software'),
    )

    access_policies = (
        (0, 'Open'),
        (1, 'Restricted'),
        (2, 'Credentialed'),
    )

    # Main body descriptive metadata

    resource_type = models.PositiveSmallIntegerField(choices=resource_types)
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

    # The additional papers to cite when citing the database
    project_citations =GenericRelation(Reference, blank=True)
    version = models.CharField(max_length=15, default='', blank=True)
    changelog_summary = RichTextField(blank=True)

    # One of three: open, dua signature, credentialed user + dua signature
    access_policy = models.SmallIntegerField(choices=access_policies,
                                             default=0)
    license = models.ForeignKey('project.License', null=True)

    # Identifiers
    external_home_page = models.URLField(blank=True, null=True)
    publications = GenericRelation(Publication, blank=True)
    topics = GenericRelation(Topic, blank=True)
    contacts = GenericRelation(Contact, blank=True)


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
    # Under any stage of the submission process, from presubmission.
    # 1 <= Submission.submission_status <= 4. The project is not
    # editable when this is True.
    under_submission = models.BooleanField(default=False)

    # Access fields
    data_use_agreement = models.ForeignKey('project.DataUseAgreement',
                                           null=True, blank=True)

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

    def submission_status(self):
        """
        The submission status is kept track of in the active Submission
        object, if it exists.
        """
        if self.under_submission:
            return self.submissions.get(is_active=True).submission_status
        else:
            return 0


    def is_publishable(self):
        """
        Whether the project can be published
        """
        self.publish_errors = []

        # Invitations
        for invitation in self.invitations.filter(is_active=True):
            self.publish_errors.append('Outstanding author invitation to %s' % invitation.email)

        # Authors
        for author in self.authors.all():
            if author.is_human:
                if not author.get_full_name():
                    self.publish_errors.append('Author %s has not fill in name' % author.user.username)
                if not author.affiliations.all():
                    self.publish_errors.append('Author %s has not filled in affiliations' % author.user.username)
            else:
                if not author.organization_name:
                    self.publish_errors.append('Organizational author with no name')
        # Metadata
        for attr in ['abstract', 'background', 'methods', 'content_description',
                     'license', 'version']:
            if not getattr(self, attr):
                self.publish_errors.append('Missing required field: %s' % attr)

        if self.access_policy and not self.data_use_agreement:
            self.publish_errors.append('Missing DUA for non-open access policy')

        if not self.contacts.filter():
            self.publish_errors.append('At least one contact is required')

        if self.publish_errors:
            return False
        else:
            return True

    def presubmit(self):
        """
        Initialize submission via the submitting author
        """
        if not self.is_publishable():
            raise Exception('Project is not publishable')

        if self.submissions.filter(is_active=True):
            raise Exception('Active submission exists')

        self.under_submission = True
        self.save()

        submission = Submission.objects.create(project=self)
        self.approve_author(self.authors.get(user=self.submitting_author))

    def approve_author(self, author):
        """
        Add an author to the active submission's approved authors.
        Triggers submission if it is the last author.
        """
        if self.submission_status() != 1:
            raise Exception('Project is not under presubmission')

        submission = self.submissions.get(is_active=True)

        if submission.submission_status == 1 and author not in submission.approved_authors.all():
            submission.approved_authors.add(author)
            # Make the submission if this was the last author
            if submission.approved_authors.count() == self.authors.filter(is_human=True).count():
                self.submit()

    def cancel_submission(self):
        """
        Cancel a submission during presubmission phase at the request
        of the submitting author
        """
        if self.submission_status != 1:
            raise Exception('Project is not under presubmission')

        submission = self.submissions.get(is_active=True)
        submission.delete()
        self.under_submission = False
        self.save()

    def withdraw_submission_approval(self, author):
        """
        Withdraw a non-submitting author's submission approval during
        presubmission phase
        """
        if self.submission_status != 1:
            raise Exception('Project is not under presubmission')

        # The `cancel_submission` function is the right one to use
        if author == self.submitting_author:
            raise Exception('Cannot withdraw submitting author.')

        submission = self.submissions.get(is_active=True)
        submission.approved_authors.remove(author)

    def submit(self):
        """
        Complete the submission after the last author agrees.
        Set the submission statuses, and get reviewers + editor
        """
        submission = self.submissions.get(is_active=True)
        submission.submission_status = 2
        submission.submission_datetime = timezone.now()
        submission.save()

    def publish(self):
        """
        Create a published version of this project
        """
        if not self.is_publishable():
            raise Exception('Nope')

        published_project = PublishedProject()

        # Direct copy over fields
        for attr in ['title', 'abstract', 'background', 'methods',
                     'content_description', 'technical_validation',
                     'usage_notes', 'acknowledgements', 'project_home_page',
                     'version', 'resource_type', 'access_policy',
                     'changelog_summary', 'access_policy', 'license']:
            setattr(published_project, attr, getattr(self, attr))

        # New content
        published_project.base_project = self
        published_project.storage_size = self.storage_used()
        # To be implemented...
        published_project.doi = '10.13026/C2F305'
        published_project.save()

        # Same content, different objects.
        for reference in self.references.all():
            reference_copy = Reference.objects.create(
                description=reference.description,
                project_object=published_project)

        for topic in self.topics.all():
            published_topic = PublishedTopic.objects.filter(description=topic.description.lower())
            # If same content object exists, add it. Otherwise create.
            if published_topic.count():
                published_project.topics.add(published_topic.first())
            else:
                published_topic = PublishedTopic.objects.create(description=topic.description.lower())
                published_project.topics.add(published_topic)

        for author in self.authors.all():
            if author.is_human:
                first_name, middle_names, last_name = author.user.get_names()
            else:
                first_name, middle_names, last_name = '', '', ''

            author_copy = Author.objects.create(
                published_project=published_project,
                first_name=first_name, middle_names=middle_names,
                last_name=last_name, is_human=author.is_human,
                organization_name=author.organization_name,
                display_order=author.display_order, #'affiliations',
                user=author.user
                )

        # Non-open access policy
        if self.access_policy:
            access_system = AccessSystem.objects.create(
                name=published_project.__str__(),
                license=self.license,
                data_use_agreement=self.data_use_agreement,
                requires_credentialed=bool(self.access_policy-1)
                )
            published_project.access_system = access_system


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
    # The Project this object was created from
    base_project = models.ForeignKey('project.Project',
        related_name='published_projects', blank=True, null=True)
    topics = models.ManyToManyField('project.PublishedTopic',
                                    related_name='tagged_projects')
    # Total file storage size in bytes
    storage_size = models.IntegerField()
    publish_datetime = models.DateTimeField(auto_now_add=True)
    is_newest_version = models.BooleanField(default=True)
    doi = models.CharField(max_length=50, default='', unique=True)

    access_system = models.ForeignKey('project.AccessSystem',
                                       related_name='projects')

    class Meta:
        unique_together = (('base_project', 'version'),)

    def __str__(self):
        return ('%s v%s' % (self.title, self.version))


class License(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    description = RichTextField()
    url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name


class DataUseAgreement(models.Model):
    """
    Data use agreement, for PublishedProjects via their AccessSystem.
    """
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170)
    description = RichTextField()
    creation_datetime = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class AccessSystem(models.Model):
    """
    Access control for published projects. This is a separate model
    so that multiple published projects can share the same
    access system and list of approved users.

    Also we use this intermediate object to change the dua/license
    for a published project without publishing a new version

    """
    name = models.CharField(max_length=100, unique=True)
    # This license field is used if the PublishedProject has an
    # AccessSystem object (not open). Otherwise the
    # PublishedProject.license field is used.
    license = models.ForeignKey('project.License')
    data_use_agreement = models.ForeignKey('project.DataUseAgreement')
    requires_credentialed = models.BooleanField(default=False)
    creation_datetime = models.DateTimeField(auto_now_add=True)


class Approval(models.Model):
    """
    Object indicating that a user is approved to access a project
    """
    access_system = models.ForeignKey('project.AccessSystem')
    user = models.ForeignKey('user.User')
    first_approval_datetime = models.DateTimeField()
    approval_datetime = models.DateTimeField()
    requires_update = models.BooleanField(default=False)


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

    def __str__(self):
        return "%dGB for project: %s" % (self.request_allowance, self.project.__str__())


class Submission(models.Model):
    """
    Project submission. Object is created in presubmission mode when
    submitting author submits. When all co-authors approve, official
    submission begins. Object can be deleted if submitting author
    retracts before all co-authors approve.

    The submission_status field:
    - 1 : submitting author submits.
    - 2 : all authors agree.
    - 3 : editor assigned, awaiting decision.
    - 4 : decision 1 = resubmission requested (accept with changes).
          Loops back to 3.
    - 5 : decision 2 = hard reject, final.
    - 6 : decision 3 = accept, awaiting author approval to publish.
    - 7 : author approves publishing, and project is published.

    """
    project = models.ForeignKey('project.Project', related_name='submissions')
    # Each project can have one active submission at a time
    is_active = models.BooleanField(default=True)
    submission_status = models.PositiveSmallIntegerField(default=1)
    approved_authors = models.ManyToManyField('project.Author')
    # Marks when the submitting author submits
    presubmission_datetime = models.DateTimeField(auto_now_add=True)
    # Marks when all co-authors approve
    submission_datetime = models.DateTimeField(null=True)
    # Marks when the editor decides the final accept/reject
    response_datetime = models.DateTimeField(null=True)
    editor = models.ForeignKey('user.User', related_name='editing_submissions',
        null=True)
    # Comments for the final decision
    editor_comments = models.CharField(max_length=800)
    # Set to 0 for reject or 1 for accept, when final decision is made.
    response = models.NullBooleanField(null=True)


class Resubmission(models.Model):
    """
    Model for resubmissions, ie. when editor accepts with conditional
    changes.

    """
    submission = models.ForeignKey('project.Submission',
        related_name='resubmissions')
    response_datetime = models.DateTimeField(null=True)
    # Comments for this resubmission decision
    editor_comments = models.CharField(max_length=800)
    is_active = models.BooleanField(default=True)


class Review(models.Model):
    """
    A review for a submission
    """
    submission = models.ForeignKey('project.Submission', related_name='reviews')
    user = models.ForeignKey('user.User', related_name='reviews')
    comments = models.CharField(max_length=800)
    decision = models.NullBooleanField(null=True)
    is_active = models.BooleanField(default=True)
    response_datetime = models.DateTimeField(null=True)

