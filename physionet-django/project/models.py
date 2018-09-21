import os
import shutil
import pdb

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
from .utility import get_tree_size, get_file_info, get_directory_info, list_items


def new_creation(receiver_function):
    """
    Decorator for a receiver function to only trigger upon model
    creation from non-fixtures.
    """
    def func_wrapper(*args, **kwargs):
        if kwargs.get('created') and not kwargs.get('raw'):
            return receiver_function(*args, **kwargs)

    return func_wrapper


class Affiliation(models.Model):
    """
    Affiliations belonging to an author

    """
    name = models.CharField(max_length=255)
    author = models.ForeignKey('project.Author', related_name='affiliations')

    class Meta:
        unique_together = (('name', 'author'),)


class Author(models.Model):
    """
    A project's author/creator (datacite). Credited for creating the
    resource.

    Datacite definition: "The main researchers involved in producing the
    data, or the authors of the publication, in priority order."

    This model is used for both Project and PublishedProject
    """
    project = models.ForeignKey('project.Project', related_name='%(class)ss',
        null=True, blank=True)
    published_project =models.ForeignKey('project.PublishedProject',
        related_name='%(class)ss', null=True, blank=True)
    approved_publish = models.BooleanField(default=False)
    user = models.ForeignKey('user.User', related_name='authorships')
    first_name = models.CharField(max_length=100, default='')
    middle_names = models.CharField(max_length=200, default='')
    last_name = models.CharField(max_length=100, default='')
    display_order = models.PositiveSmallIntegerField()
    is_corresponding = models.BooleanField(default=False)
    corresponding_email = models.ForeignKey('user.AssociatedEmail', null=True)

    class Meta:
        unique_together = (('user', 'project'), ('user', 'published_project'),)

    def __str__(self):
        return '{} --- {}'.format(self.user.username, self.corresponding_email)

    def display_affiliation(self):
        return ', '.join([a.name for a in self.affiliations.all()])

    def get_full_name(self):
        if self.middle_names:
            return ' '.join([self.first_name, self.middle_names,
                           self.last_name])
        else:
            return ' '.join([self.first_name, self.last_name])

    def disp_name_email(self):
        return '{} -- {}'.format(self.get_full_name(), self.user.email)

    def import_profile_info(self):
        """
        Import profile information (names) into the Author object.
        Also create affiliation object if present in profile.

        To be called when an author object is created
        """
        profile = self.user.profile
        for field in ['first_name', 'middle_names', 'last_name']:
            setattr(self, field, getattr(profile, field))
        self.save()

        if profile.affiliation:
            Affiliation.objects.create(name=profile.affiliation,
                author=self)


class Topic(models.Model):
    """
    Topic information to tag projects
    """
    description = models.CharField(max_length=50)
    project = models.ForeignKey('project.Project', related_name='topics')

    class Meta:
        unique_together = (('description', 'project'),)

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
    Reference field for Project/PublishedProject
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
    """
    Contact for a PublishedProject
    """
    name = models.CharField(max_length=120)
    affiliations = models.CharField(max_length=150)
    email = models.EmailField(max_length=255)
    published_project = models.ForeignKey('project.PublishedProject',
        related_name='contacts')


class Publication(models.Model):
    """
    The publication to cite when referencing the software/dataset.
    """
    citation = models.CharField(max_length=250)
    url = models.URLField(blank=True, default='')

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

    RESOURCE_TYPES = (
        (0, 'Database'),
        (1, 'Software'),
    )

    ACCESS_POLICIES = (
        (0, 'Open'),
        (1, 'Restricted'),
        (2, 'Credentialed'),
    )

    resource_type = models.PositiveSmallIntegerField(choices=RESOURCE_TYPES)

    # Main body descriptive metadata

    title = models.CharField(max_length=200)
    abstract = RichTextField(max_length=10000, blank=True)
    background = RichTextField(blank=True)
    methods = RichTextField(blank=True)
    content_description = RichTextField(blank=True)
    usage_notes = RichTextField(blank=True)
    references = GenericRelation(Reference, blank=True)
    acknowledgements = RichTextField(blank=True)
    conflicts_of_interest = RichTextField(blank=True)
    version = models.CharField(max_length=15, default='', blank=True)
    changelog_summary = RichTextField(blank=True)

    # Supplementary descriptive fields

    # The additional papers to cite when citing the database
    project_citations = GenericRelation(Reference, blank=True)

    # Access information
    access_policy = models.SmallIntegerField(choices=ACCESS_POLICIES,
                                             default=0)
    license = models.ForeignKey('project.License', null=True)

    # Identifiers
    publications = GenericRelation(Publication, blank=True)
    topics = GenericRelation(Topic, blank=True)


class Project(Metadata):
    """
    The model for user-owned projects.
    """
    creation_datetime = models.DateTimeField(auto_now_add=True)
    modified_datetime = models.DateTimeField(auto_now=True)

    # Maximum allowed storage capacity in GB
    storage_allowance = models.SmallIntegerField(default=1)
    # Misnomers - actually a User object, not an Author object.
    submitting_author = models.ForeignKey('user.User',
        related_name='submitting_projects')
    # If it has any published versions
    published = models.BooleanField(default=False)
    # Under any stage of the submission process, from presubmission.
    # 1 <= Submission.submission_status <= 4. The project is not
    # editable when this is True.
    under_submission = models.BooleanField(default=False)
    # Access fields
    data_use_agreement = models.ForeignKey('project.DataUseAgreement',
                                           null=True, blank=True)

    INDIVIDUAL_FILE_SIZE_LIMIT = 100 * 1024**2

    REQUIRED_FIELDS = {0:['title', 'abstract', 'background', 'methods',
                          'content_description', 'conflicts_of_interest',
                          'version', 'license',],
                       1:['title', 'abstract', 'background', 'methods',
                          'content_description', 'conflicts_of_interest',
                          'version', 'license',]}

    class Meta:
        unique_together = (('title', 'submitting_author', 'resource_type'),)

    def __str__(self):
        return self.title

    def corresponding_author(self):
        return self.authors.get(is_corresponding=True)

    def file_root(self):
        "Root directory containing the project's files"
        return os.path.join(settings.MEDIA_ROOT, 'project', str(self.id))

    def storage_used(self):
        "Total storage used in bytes"
        return get_tree_size(self.file_root())

    def get_directory_content(self, subdir=''):
        """
        Return information for displaying file and directories
        """
        inspect_dir = os.path.join(self.file_root(), subdir)
        file_names , dir_names = list_items(inspect_dir)
        display_files, display_dirs = [], []

        # Files require desciptive info and download links
        for file in file_names:
            file_info = get_file_info(os.path.join(inspect_dir, file))
            file_info.full_file_name = os.path.join(subdir, file)
            display_files.append(file_info)

        # Directories require
        for dir_name in dir_names:
            dir_info = get_directory_info(os.path.join(inspect_dir, dir_name))
            dir_info.full_subdir = os.path.join(subdir, dir_name)
            display_dirs.append(dir_info)

        return display_files, display_dirs

    def submission_status(self):
        """
        The submission status is kept track of in the active Submission
        object, if it exists.
        """
        if self.under_submission:
            return self.submissions.get(is_active=True).submission_status
        else:
            return -1

    def is_frozen(self):
        """
        Project is not editable when frozen
        """
        if self.submission_status() in [0, 4]:
            return False
        else:
            return True

    def get_coauthors(self):
        """
        Return queryset of non-submitting authors
        """
        return self.authors.exclude(user=self.submitting_author)

    def get_coauthor_info(self):
        """
        Return tuple pairs of non-submitting author emails and names
        """
        return ((a.user.email, a.user.get_full_name()) for a in self.get_coauthors())

    def get_submitting_author_info(self):
        """
        Return the email and name of the submitting author
        """
        return self.submitting_author.email, self.submitting_author.get_full_name()

    def get_author_info(self):
        """
        Return tuple pairs of all author emails and names
        """
        return ((a.user.email, a.user.get_full_name()) for a in self.authors.all())

    def is_submittable(self):
        """
        Run integrity tests on metadata fields and return whether the
        project can be submitted
        """
        self.submit_errors = []

        # Invitations
        for invitation in self.invitations.filter(is_active=True):
            self.submit_errors.append(
                'Outstanding author invitation to {0}'.format(invitation.email))

        # Authors
        for author in self.authors.all():
            if not author.get_full_name():
                self.submit_errors.append('Author {0} has not fill in name'.format(author.user.username))
            if not author.affiliations.all():
                self.submit_errors.append('Author {0} has not filled in affiliations'.format(author.user.username))

        # Metadata
        for attr in Project.REQUIRED_FIELDS[self.resource_type]:
            if not getattr(self, attr):
                self.submit_errors.append('Missing required field: {0}'.format(attr.replace('_', ' ')))

        if self.access_policy and not self.data_use_agreement:
            self.submit_errors.append('Missing DUA for non-open access policy')

        if self.published:
            published_versions = [p.version for p in self.published_projects.all()]
            if self.version in published_versions:
                self.submit_errors.append('The version matches a previously published version.')

        if self.submit_errors:
            return False
        else:
            return True

    def submit(self):
        """
        Complete the submission after the last author agrees.
        Set the submission statuses, and get reviewers + editor
        """
        if not self.is_submittable():
            raise Exception('Project is not submittable')

        if self.submissions.filter(is_active=True):
            raise Exception('Active submission exists')

        self.under_submission = True
        self.save()
        Submission.objects.create(project=self)

    def publish(self):
        """
        Create a published version of this project and update the
        submission status
        """
        if not self.is_submittable():
            raise Exception('Nope')

        published_project = PublishedProject()

        # Direct copy over fields
        for attr in ['title', 'abstract', 'background', 'methods',
                     'content_description', 'usage_notes', 'acknowledgements',
                     'conflicts_of_interest', 'version', 'resource_type',
                     'access_policy', 'changelog_summary', 'access_policy',
                     'license']:
            setattr(published_project, attr, getattr(self, attr))

        # New content
        published_project.base_project = self
        published_project.storage_size = self.storage_used()
        published_project.save()

        # Same content, different objects.
        for reference in self.references.all():
            reference_copy = Reference.objects.create(
                description=reference.description,
                project_object=published_project)

        for publication in self.publications.all():
            publication_copy = Publication.objects.create(
                citation=publication.citation, url=publication.url,
                project_object=published_project)

        for topic in self.topics.all():
            published_topic = PublishedTopic.objects.filter(
                description=topic.description.lower())
            # If same content object exists, add it. Otherwise create.
            if published_topic.count():
                published_project.topics.add(published_topic.first())
            else:
                published_topic = PublishedTopic.objects.create(
                    description=topic.description.lower())
                published_project.topics.add(published_topic)

        for author in self.authors.all():
            author_copy = Author.objects.create(
                published_project=published_project,
                first_name=author.first_name, middle_names=author.middle_names,
                last_name=author.last_name, display_order=author.display_order,
                user=author.user
                )

            affiliations = author.affiliations.all()
            for affiliation in affiliations:
                affiliation_copy = Affiliation.objects.create(
                    name=affiliation.name, author=author_copy)

        corresponding_author = self.authors.get(is_corresponding=True)
        contact = Contact.objects.create(name=corresponding_author.get_full_name(),
            affiliations=corresponding_author.display_affiliation(),
            email=corresponding_author.corresponding_email,
            published_project=published_project)

        # Non-open access policy
        if self.access_policy:
            access_system = AccessSystem.objects.create(
                name=published_project.__str__(),
                license=self.license,
                data_use_agreement=self.data_use_agreement,
                requires_credentialed=bool(self.access_policy-1)
                )
            published_project.access_system = access_system
            published_project.save()

        # Copy over files
        shutil.copytree(self.file_root(), published_project.file_root())

        self.under_submission = False
        self.published = True
        self.save()
        self.authors.all().update(approved_publish=False)

        return published_project

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
    author = Author.objects.create(project=project, user=user, display_order=1,
        corresponding_email=user.get_primary_email(), is_corresponding=True)
    author.import_profile_info()
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
    doi = models.CharField(max_length=50, default='')
    doi_assigned = models.BooleanField(default=False)

    access_system = models.ForeignKey('project.AccessSystem', null=True,
                                       related_name='projects')

    class Meta:
        unique_together = (('base_project', 'version'),)

    def __str__(self):
        return ('{0} v{1}'.format(self.title, self.version))

    def validate_doi(self, *args, **kwargs):
        """
        Validate uniqueness of doi, ignore empty ''
        """
        super().validate_unique(*args, **kwargs)
        print('n\n\\n\nLAOEIFJAOEIFEAF\n\n\n\n')

        published_projects = __class__.objects.filter(doi_assigned=True)
        dois = [p.doi for p in published_projects]

        if len(dois) != len(set(dois)):
            raise ValidationError('Duplicate DOI')

    def file_root(self):
        "Root directory containing the published project's files"
        if self.access_policy:
            return os.path.join(settings.MEDIA_ROOT, 'published-project', str(self.id))
        else:
            # Temporary workaround for development
            if os.environ['DJANGO_SETTINGS_MODULE'] == 'physionet.settings.development':
                return os.path.join(settings.STATICFILES_DIRS[0], 'published-project', str(self.id))
            else:
                return os.path.join(settings.STATIC_ROOT, 'published-project', str(self.id))

    def get_directory_content(self, subdir=''):
        """
        Return information for displaying file and directories
        """
        inspect_dir = os.path.join(self.file_root(), subdir)
        file_names , dir_names = list_items(inspect_dir)

        display_files, display_dirs = [], []

        # Files require desciptive info and download links
        for file in file_names:
            file_info = get_file_info(os.path.join(inspect_dir, file))
            if self.access_policy:
                file_info.full_file_name = os.path.join(subdir, file)
            else:
                file_info.static_url = os.path.join('published-project', str(self.id), subdir, file)
            display_files.append(file_info)

        # Directories require
        for dir_name in dir_names:
            dir_info = get_directory_info(os.path.join(inspect_dir, dir_name))
            dir_info.full_subdir = os.path.join(subdir, dir_name)
            display_dirs.append(dir_info)

        return display_files, display_dirs


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
        return 'Project: {0} To: {1} By: {2}'.format(self.project, self.email,
                                                     self.inviter)

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
        return '{0}GB for project: {1}'.format(self.request_allowance,
                                               self.project.__str__())


class BaseSubmission(models.Model):
    """
    Class to be inherited by Submission and Resubmission

    """
    # Each project can have one active submission at a time
    is_active = models.BooleanField(default=True)
    # When the submitting author submits
    submission_datetime = models.DateTimeField(auto_now_add=True)
    # Editor decision. 1 2 or 3 for reject/revise/accept
    decision = models.SmallIntegerField(null=True)
    decision_datetime = models.DateTimeField(null=True)
    # Comments for the decision
    editor_comments = models.CharField(max_length=800)

    class Meta:
        abstract = True


class Submission(BaseSubmission):
    """
    Project submission. Object is created when submitting author submits.

    The submission_status field:
    - 0 : submitting author submits. Awaiting decision.
    - 1 : decision 1 = reject.
    - 2 : decision 2 = accept with revisions.
    - 3 : decision 3 = accept. In copyedit stage.
    - 4 : copyedit complete. Waiting for authors to approve publish.
    - 5 : all authors approved publish. ready for editor to publish
    - 10 : published

    """
    project = models.ForeignKey('project.Project', related_name='submissions')
    # Editor is manually assigned
    editor = models.ForeignKey('user.User', related_name='editing_submissions',
        null=True)
    submission_status = models.PositiveSmallIntegerField(default=0)

    # The published item, if decision is accept
    published_project = models.OneToOneField('project.PublishedProject',
        null=True, related_name='publishing_submission')
    publish_datetime = models.DateTimeField(null=True)

    def __str__(self):
        return 'Submission ID {0} - {1}'.format(self.id, self.project.title)

    def all_authors_approved(self):
        authors = self.project.authors.all()
        return len(authors) == sum(a.approved_publish for a in authors)

    def get_active_resubmission(self):
        if self.is_active:
            return self.resubmissions.get(is_active=True)

    def get_resubmissions(self):
        return self.resubmissions.all().order_by('creation_datetime')


class Resubmission(BaseSubmission):
    """
    Model for resubmissions, ie. when editor accepts with conditional
    changes.

    The object is created when the submitting author makes a resubmission.

    """
    submission = models.ForeignKey('project.Submission',
        related_name='resubmissions')
