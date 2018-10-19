import os
import shutil
import uuid
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
from django.utils.crypto import get_random_string

from user.models import User
from .utility import get_tree_size, get_file_info, get_directory_info, list_items


class Affiliation(models.Model):
    """
    Affiliations belonging to an author

    """
    name = models.CharField(max_length=255)
    author = models.ForeignKey('project.Author', related_name='affiliations')

    class Meta:
        unique_together = (('name', 'author'),)


class BaseAuthor(models.Model):
    """
    Base model for a project's author/creator. Credited for creating the
    resource.

    Datacite definition: "The main researchers involved in producing the
    data, or the authors of the publication, in priority order."
    """
    user = models.ForeignKey('user.User', related_name='%(class)ss')
    display_order = models.PositiveSmallIntegerField()
    is_submitting = models.BooleanField(default=False)
    is_corresponding = models.BooleanField(default=False)

    class Meta:
        abstract = True


class Author(BaseAuthor):
    """
    The author model for ArchivedProject/ActiveProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')
    corresponding_email = models.ForeignKey('user.AssociatedEmail', null=True)
    approved_publish = models.BooleanField(default=False)

    class Meta:
        unique_together = (('user', 'content_type', 'object_id',),)

    def __str__(self):
        # Best representation for form display
        user = self.user
        return '{} --- {}'.format(user.username, user.email)

    def get_full_name(self):
        """
        The name is tied to the profile. There is no form for authors
        to change their names
        """
        return self.user.profile.get_full_name()

    def disp_name_email(self):
        return '{} ({})'.format(self.get_full_name(), self.user.email)

    def import_profile_info(self):
        """
        Import profile information (names) into the Author object.
        Also create affiliation object if present in profile.

        """
        profile = self.user.profile
        if profile.affiliation:
            Affiliation.objects.create(name=profile.affiliation,
                author=self)

    def set_display_info(self, set_affiliations=True):
        """
        Set the fields used to display the author
        """
        user = self.user
        self.name = user.profile.get_full_name
        self.email = user.email
        self.username = user.username

        if set_affiliations:
            self.text_affiliations = [a.name for a in self.affiliations.all()]


class PublishedAuthor(BaseAuthor):
    """
    The author model for PublishedProject
    """
    first_name = models.CharField(max_length=100, default='')
    middle_names = models.CharField(max_length=200, default='')
    last_name = models.CharField(max_length=100, default='')

    published_project = models.ForeignKey('project.PublishedProject',
        related_name='authors', db_index=True)

    class Meta:
        unique_together = (('user', 'published_project'),)


class Topic(models.Model):
    """
    Topic information to tag ActiveProject/ArchivedProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    description = models.CharField(max_length=50)

    class Meta:
        unique_together = (('description', 'content_type', 'object_id'),)

    def __str__(self):
        return self.description


class PublishedTopic(models.Model):
    """
    Topic information to tag PublishedProject
    """
    description = models.CharField(max_length=50)

    def __str__(self):
        return self.description


class Reference(models.Model):
    """
    Reference field for ActiveProject/ArchivedProject
    """
    description = models.CharField(max_length=250)

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


class BasePublication(models.Model):
    """
    Base model for the publication to cite when referencing the
    resource
    """
    citation = models.CharField(max_length=250)
    url = models.URLField(blank=True, default='')

    class Meta:
        abstract = True

class Publication(BasePublication):
    """
    Publication for ArchivedProject/ActiveProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')


class PublishedPublication(BasePublication):
    """
    """
    published_project = models.ForeignKey('project.PublishedProject',
        db_index=True)


class CoreProject(models.Model):
    """
    The core underlying object that links all versions of the project in
    its various states
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creation_datetime = models.DateTimeField(auto_now_add=True)
    # doi pointing to the latest version of the published project
    doi = models.CharField(max_length=50, default='')
    # Maximum allowed storage capacity in MB
    storage_allowance = models.PositiveIntegerField(default=100)


class Metadata(models.Model):
    """
    Metadata for all projects

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
    data_use_agreement = models.ForeignKey('project.DataUseAgreement',
                                           null=True, blank=True)

    # Identifiers
    publications = GenericRelation(Publication, blank=True)
    topics = GenericRelation(Topic, blank=True)

    # Public url slug, also used as a submitting project id.
    slug = models.SlugField(max_length=20, unique=True, db_index=True)
    core_project = models.ForeignKey('project.CoreProject',
                                     related_name='%(class)ss')
    # When the submitting project was created
    creation_datetime = models.DateTimeField(auto_now_add=True)


class UnpublishedProject(models.Model):
    """
    Abstract model inherited by ArchivedProject/ActiveProject
    """
    modified_datetime = models.DateTimeField(auto_now=True)

    authors = GenericRelation('project.Author')
    references = GenericRelation('project.Reference')
    publications = GenericRelation('project.Publication')
    topics = GenericRelation('project.Topic')

    submission_log = GenericRelation('project.SubmissionLog')

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    def corresponding_author(self):
        return self.authors.get(is_corresponding=True)

    def submitting_author(self):
        return self.authors.get(is_submitting=True)


class ArchivedProject(Metadata, UnpublishedProject):
    """
    An archived project. Created when (maps to archive_reason):
    1. A user chooses to 'delete' their ActiveProject.
    2. An ActiveProject is not submitted for too long.
    3. An ActiveProject is submitted and rejected.
    4. An ActiveProject is submitted and times out.
    """
    archive_datetime = models.DateTimeField(auto_now_add=True)
    archive_reason = models.PositiveSmallIntegerField()

    def file_root(self):
        "Root directory containing the project's files"
        return os.path.join(settings.MEDIA_ROOT, 'archived-project', str(self.id))


class ActiveProject(Metadata, UnpublishedProject):
    """
    The project used for submitting

    The submission_status field:
    - 0 : Not submitted
    - 10 : Submitting author submits. Awaiting editor assignment.
    - 20 : Editor assigned. Awaiting editor decision.
    - 30 : Accepted with revisions. Waiting for resubmission. Loops back
          to 20 when author resubmits.
    - 40 : Accepted. In copyedit stage. Awaiting editor to copyedit.
    - 50 : Editor completes copyedit. Awaiting authors to approve.
    - 60 : Authors approve copyedit. Ready for editor to publish

    """
    submission_status = models.PositiveSmallIntegerField(default=0)
    editor = models.ForeignKey('user.User', null=True)
    submission_datetime = models.DateTimeField(null=True)

    INDIVIDUAL_FILE_SIZE_LIMIT = 10 * 1024**3

    REQUIRED_FIELDS = {0:['title', 'abstract', 'background', 'methods',
                          'content_description', 'conflicts_of_interest',
                          'version', 'license',],
                       1:['title', 'abstract', 'background', 'methods',
                          'content_description', 'conflicts_of_interest',
                          'version', 'license',]}

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

    def under_submission(self):
        """
        Whether the project is under submission
        """
        return bool(self.submission_status)

    def author_editable(self):
        """
        Whether the project can be edited by its authors
        """
        if self.submission_status in [0, 30]:
            return True

    def copyeditable(self):
        """
        Whether the project can be copyedited
        """
        if self.submission_status in [40, 50]:
            return True

    def get_coauthors(self):
        """
        Return queryset of non-submitting authors
        """
        return self.authors.filter(is_submitting=False)

    def get_coauthor_info(self):
        """
        Return tuple pairs of non-submitting author emails and names
        """
        return ((a.user.email, a.user.get_full_name()) for a in self.get_coauthors())

    def get_submitting_author_info(self):
        """
        Return the email and name of the submitting author
        """
        user = self.submitting_author().user
        return user.email, user.get_full_name()

    def get_author_info(self, separate_submitting=False, include_emails=False):
        """
        Get the project's authors, setting information needed to display
        their attributes.
        """
        authors = self.authors.all().order_by('display_order')
        author_emails = ';'.join(a.user.email for a in authors)

        if separate_submitting:
            submitting_author = authors.get(is_submitting=True)
            coauthors = authors.filter(is_submitting=False)
            submitting_author.set_display_info()
            for a in coauthors:
                a.set_display_info()
            r = (submitting_author, coauthors)
        else:
            for a in authors:
                a.set_display_info()
            r = (authors,)

        if include_emails:
            r = r + (author_emails,)

        return r


    def archive(self, reason):
        """
        Archive the project. Create an ArchivedProject object, copy over
        the fields, and delete this object
        """
        ArchivedProject.objects.create(archive_reason=reason)
        self.delete()

    def is_submittable(self):
        """
        Run integrity tests on metadata fields and return whether the
        project can be submitted
        """
        self.submit_errors = []

        # Invitations
        for invitation in self.authorinvitations.filter(is_active=True):
            self.submit_errors.append(
                'Outstanding author invitation to {0}'.format(invitation.email))

        # Authors
        for author in self.authors.all():
            if not author.get_full_name():
                self.submit_errors.append('Author {0} has not fill in name'.format(author.user.username))
            if not author.affiliations.all():
                self.submit_errors.append('Author {0} has not filled in affiliations'.format(author.user.username))

        # Metadata
        for attr in ActiveProject.REQUIRED_FIELDS[self.resource_type]:
            if not getattr(self, attr):
                self.submit_errors.append('Missing required field: {0}'.format(attr.replace('_', ' ')))

        if self.access_policy and not self.data_use_agreement:
            self.submit_errors.append('Missing DUA for non-open access policy')

        published_projects = self.core_project.publishedprojects.all()
        if published_projects:
            published_versions = [p.version for p in published_projects]
            if self.version in published_versions:
                self.submit_errors.append('The version matches a previously published version.')

        if self.submit_errors:
            return False
        else:
            return True

    def submit(self):
        """
        Submit the project for review.
        """
        if not self.is_submittable():
            raise Exception('ActiveProject is not submittable')

        # This should never be the case
        if self.submission_log.filter() or self.submission_status:
            raise Exception('Duplicate submission log')

        self.submission_status = 10
        self.submission_datetime = timezone.now()
        self.save()
        # Create the submission log
        SubmissionLog.objects.create(project=self)

    def set_submitting_author(self):
        """
        Used to save query time in templates
        """
        self.submitting_author = self.submitting_author()

    def assign_editor(self, editor):
        """
        Assign an editor to the project
        """
        self.editor = editor
        self.submission_status = 20
        self.save()

    def accept_datetime(self):
        """
        When the project was accepted by the editor
        """
        if self.submission_status in [40, 50, 60]:
            submission_log = self.submission_log.get()
            # Need to account for resubmissions
            return submission_log.decision_datetime

    def all_authors_approved(self):
        "Whether all authors have approved the publication"
        authors = self.authors.all()
        return len(authors) == len(authors.filter(approved_publish=True))

    def is_publishable(self):
        """
        Check whether a project may be published
        """
        submission = self.submissions.get(is_active=True)

        if submission.status == 4 and submission.all_authors_approved():
            return True
        else:
            return False

    def publish(self):
        """
        Create a published version of this project and update the
        submission status
        """
        if not self.is_publishable():
            raise Exception('The project is not publishable')

        published_project = PublishedProject()

        # Direct copy over fields
        for attr in ['title', 'abstract', 'background', 'methods',
                     'content_description', 'usage_notes', 'acknowledgements',
                     'conflicts_of_interest', 'version', 'resource_type',
                     'access_policy', 'changelog_summary', 'access_policy',
                     'license']:
            setattr(published_project, attr, getattr(self, attr))

        # New content
        published_project.core_project = self.core_project
        published_project.storage_size = self.storage_used()
        # Generate a new slug
        slug = get_random_string(20)
        while PublishedProject.objects.filter(slug=slug):
            slug = get_random_string(20)
        published_project.slug = slug
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
            # Tag the published project with the topic. Create the published
            # topic first if it doesn't exist
            if published_topic.count():
                published_project.topics.add(published_topic.first())
            else:
                published_topic = PublishedTopic.objects.create(
                    description=topic.description.lower())
                published_project.topics.add(published_topic)

        for author in self.authors.all():
            author_copy = Author.objects.create(
                published_project=published_project,
                first_name=author.user.first_name, middle_names=author.user.middle_names,
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

        submission = self.submissions.get(is_active=True)
        submission.submission_status = 6
        submission.is_active = False
        submission.save()

        return published_project


@receiver(pre_delete, sender=ActiveProject)
def cleanup_project(sender, **kwargs):
    """
    Before a ActiveProject is deleted:
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
    # Total file storage size in bytes
    storage_size = models.PositiveIntegerField()
    publish_datetime = models.DateTimeField(auto_now_add=True)
    is_newest_version = models.BooleanField(default=True)
    newest_version = models.ForeignKey('project.PublishedProject', null=True,
                                       related_name='older_versions')
    doi = models.CharField(max_length=50, default='')

    class Meta:
        unique_together = (('core_project', 'version'),)

    def __str__(self):
        return ('{0} v{1}'.format(self.title, self.version))

    def validate_doi(self, *args, **kwargs):
        """
        Validate uniqueness of doi, ignore empty ''
        """
        super().validate_unique(*args, **kwargs)
        published_projects = __class__.objects.all()
        dois = [p.doi for p in published_projects if doi]

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
    Base class for authorship invitations and storage requests
    """
    project = models.ForeignKey('project.ActiveProject', related_name='%(class)ss')
    request_datetime = models.DateTimeField(auto_now_add=True)
    response_datetime = models.DateTimeField(null=True)
    response = models.NullBooleanField(null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class AuthorInvitation(BaseInvitation):
    """
    Invitation to join a project as an author

    """
    # The target email
    email = models.EmailField(max_length=255)
    # User who made the invitation
    inviter = models.ForeignKey('user.User')

    def __str__(self):
        return 'ActiveProject: {0} To: {1} By: {2}'.format(self.project, self.email,
                                                     self.inviter)

    def get_user_invitations(user, exclude_duplicates=True):
        """
        Get all active author invitations to a user

        """
        emails = user.get_emails()
        invitations = AuthorInvitation.objects.filter(email__in=emails,
            is_active=True).order_by('-request_datetime')

        # Remove duplicate invitations to the same project
        if exclude_duplicates:
            project_slugs = []
            remove_ids = []
            for invitation in invitations:
                if invitation.project.id in project_slugs:
                    remove_ids.append(invitation.id)
                else:
                    project_slugs.append(invitation.project.id)
            invitations = invitations.exclude(id__in=remove_ids)

        return invitations

    def is_invited(user, project):
        "Whether a user is invited to author a project"
        user_invitations = get_user_invitations(user=user)

        return bool(project in [inv.project for inv in invitations])


class StorageRequest(BaseInvitation):
    """
    A request for storage capacity for a project
    """
    # Requested storage size in GB
    request_allowance = models.SmallIntegerField(
        validators=[MaxValueValidator(100), MinValueValidator(1)])
    responder = models.ForeignKey('user.User', null=True)
    response_message = models.CharField(max_length=50, default='', blank=True)

    def __str__(self):
        return '{0}GB for project: {1}'.format(self.request_allowance,
                                               self.project.__str__())


class BaseSubmissionLog(models.Model):
    """
    Class to be inherited by SubmissionLog and ResubmissionLog

    """
    editor = models.ForeignKey('user.User', null=True)
    # When the submitting author submits/resubmits
    submission_datetime = models.DateTimeField(auto_now_add=True)
    # Quality assurance fields
    soundly_produced = models.NullBooleanField(null=True)
    well_described = models.NullBooleanField(null=True, blank=False)
    open_format = models.NullBooleanField(null=True, blank=False)
    data_machine_readable = models.NullBooleanField(null=True, blank=False)
    reusable = models.NullBooleanField(null=True, blank=False)
    no_phi = models.NullBooleanField(null=True)
    pn_suitable = models.NullBooleanField(null=True)

    # Editor decision. 1 2 or 3 for reject/revise/accept
    decision = models.SmallIntegerField(null=True)
    decision_datetime = models.DateTimeField(null=True)
    # Comments for the decision
    editor_comments = models.CharField(max_length=800)


    class Meta:
        abstract = True


class SubmissionLog(BaseSubmissionLog):
    """
    Submission log for ActiveProject/ArchivedProject

    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    editor = models.ForeignKey('user.User', related_name='editing_submissions',
        null=True)
    # When (if) the editor completes the copyedit
    copyedit_datetime = models.DateTimeField(null=True)
    # When (if) the authors approve the copyedit
    copyedit_approve_datetime = models.DateTimeField(null=True)

    class Meta:
        # Each project may have only one submission log
        unique_together = (('content_type', 'object_id'),)

    def __str__(self):
        return 'Submission ID {0} - {1}'.format(self.id, self.project.title)

    def get_resubmissions(self):
        return self.resubmissions.all().order_by('creation_datetime')

    def final_decision(self):
        """
        The final editor decision. May be contained in a resubmission
        log. May be null.
        """
        resubmissions = self.get_resubmissions()

        if resubmissions:
            return resubmissions[-1].decision
        else:
            return self.decision


class ResubmissionLog(BaseSubmissionLog):
    """
    Model for resubmissions, ie. when editor accepts with conditional
    changes.

    The object is created when the submitting author makes a resubmission.

    """
    submission = models.ForeignKey('project.SubmissionLog',
        related_name='resubmission_logs')


class PublishedSubmissionLog(BaseSubmissionLog):
    """
    Submission log for published projects
    """
    published_project = models.OneToOneField('project.PublishedProject',
        related_name='publishing_submission', db_index=True)
    editor = models.ForeignKey('user.User',
        related_name='published_submissions')


class PublishedResubmissionLog(BaseSubmissionLog):
    """
    Resubmission log for published submission
    """
    published_submission = models.ForeignKey('project.SubmissionLog',
        related_name='published_resubmission_logs', db_index=True)
