from datetime import datetime, timedelta
import hashlib
import os
import shutil
import uuid
import pdb
import pytz

from ckeditor.fields import RichTextField
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .utility import get_tree_size, get_file_info, get_directory_info, list_items, StorageInfo, get_tree_files, list_files
from .validators import validate_doi, validate_subdir
from user.validators import validate_alphaplus, validate_alphaplusplus


class Affiliation(models.Model):
    """
    Affiliations belonging to an author
    """
    name = models.CharField(max_length=202, validators=[validate_alphaplusplus])
    author = models.ForeignKey('project.Author', related_name='affiliations',
        on_delete=models.CASCADE)

    class Meta:
        unique_together = (('name', 'author'),)


class PublishedAffiliation(models.Model):
    """
    Affiliations belonging to a published author
    """
    name = models.CharField(max_length=202, validators=[validate_alphaplus])
    author = models.ForeignKey('project.PublishedAuthor',
        related_name='affiliations', on_delete=models.CASCADE)

    class Meta:
        unique_together = (('name', 'author'),)


class BaseAuthor(models.Model):
    """
    Base model for a project's author/creator. Credited for creating the
    resource.

    Datacite definition: "The main researchers involved in producing the
    data, or the authors of the publication, in priority order."
    """
    user = models.ForeignKey('user.User', related_name='%(class)ss',
        on_delete=models.CASCADE)
    display_order = models.PositiveSmallIntegerField()
    is_submitting = models.BooleanField(default=False)
    is_corresponding = models.BooleanField(default=False)
    # When they approved the project for publication
    approval_datetime = models.DateTimeField(null=True)

    class Meta:
        abstract = True

    def __str__(self):
        # Best representation for form display
        user = self.user
        return '{} --- {}'.format(user.username, user.email)


class Author(BaseAuthor):
    """
    The author model for ArchivedProject/ActiveProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')
    corresponding_email = models.ForeignKey('user.AssociatedEmail', null=True,
        on_delete=models.SET_NULL)

    class Meta:
        unique_together = (('user', 'content_type', 'object_id',),)

    def get_full_name(self):
        """
        The name is tied to the profile. There is no form for authors
        to change their names
        """
        return self.user.profile.get_full_name()

    def disp_name_email(self):
        """
        """
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
        self.name = user.profile.get_full_name()
        self.email = user.email
        self.username = user.username

        if set_affiliations:
            self.text_affiliations = [a.name for a in self.affiliations.all()]


class PublishedAuthor(BaseAuthor):
    """
    The author model for PublishedProject
    """
    first_names = models.CharField(max_length=100, default='')
    last_name = models.CharField(max_length=50, default='')
    corresponding_email = models.EmailField(null=True)
    project = models.ForeignKey('project.PublishedProject',
        related_name='authors', db_index=True, on_delete=models.CASCADE)

    class Meta:
        unique_together = (('user', 'project'),)

    def get_full_name(self):
        return ' '.join([self.first_names, self.last_name])

    def set_display_info(self):
        """
        Set the fields used to display the author
        """
        self.name = self.get_full_name()
        self.username = self.user.username
        self.email = self.user.email
        self.text_affiliations = [a.name for a in self.affiliations.all()]

    def initialed_name(self):
        return '{}, {}'.format(self.last_name, ' '.join('{}.'.format(i[0]) for i in self.first_names.split()))


class Topic(models.Model):
    """
    Topic information to tag ActiveProject/ArchivedProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    description = models.CharField(max_length=50, validators=[validate_alphaplus])

    class Meta:
        unique_together = (('description', 'content_type', 'object_id'),)

    def __str__(self):
        return self.description


class PublishedTopic(models.Model):
    """
    Topic information to tag PublishedProject
    """
    projects = models.ManyToManyField('project.PublishedProject',
        related_name='topics')
    description = models.CharField(max_length=50, validators=[validate_alphaplus])
    project_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.description


class Reference(models.Model):
    """
    Reference field for ActiveProject/ArchivedProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    description = models.CharField(max_length=1000)

    class Meta:
        unique_together = (('description', 'content_type', 'object_id'),)

    def __str__(self):
        return self.description


class PublishedReference(models.Model):
    """
    """
    description = models.CharField(max_length=1000)
    project = models.ForeignKey('project.PublishedProject',
        related_name='references', on_delete=models.CASCADE)

    class Meta:
        unique_together = (('description', 'project'))


class Contact(models.Model):
    """
    Contact for a PublishedProject
    """
    name = models.CharField(max_length=120)
    affiliations = models.CharField(max_length=150)
    email = models.EmailField(max_length=255)
    project = models.ForeignKey('project.PublishedProject',
        related_name='contacts', on_delete=models.CASCADE)


class BasePublication(models.Model):
    """
    Base model for the publication to cite when referencing the
    resource
    """
    citation = models.CharField(max_length=1000)
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
    Publication for published project
    """
    project = models.ForeignKey('project.PublishedProject',
        db_index=True, related_name='publications', on_delete=models.CASCADE)


class CoreProject(models.Model):
    """
    The core underlying object that links all versions of the project in
    its various states
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creation_datetime = models.DateTimeField(auto_now_add=True)
    # doi pointing to the latest version of the published project
    doi = models.CharField(max_length=50, default='')
    # Maximum allowed storage capacity in bytes.
    # Default = 100Mb. Max = 10Tb
    storage_allowance = models.BigIntegerField(default=104857600,
        validators=[MaxValueValidator(109951162777600),
                    MinValueValidator(104857600)])


class Metadata(models.Model):
    """
    Metadata for all projects

    https://schema.datacite.org/
    https://schema.datacite.org/meta/kernel-4.0/doc/DataCite-MetadataKernel_v4.1.pdf
    https://www.nature.com/sdata/publish/for-authors#format
    """
    RESOURCE_TYPES = (
        (0, 'Database'),
        (1, 'Software'),
        (2, 'Challenge'),
    )

    ACCESS_POLICIES = (
        (0, 'Open'),
        (1, 'Restricted'),
        (2, 'Credentialed'),
    )

    resource_type = models.PositiveSmallIntegerField(choices=RESOURCE_TYPES)

    # Main body descriptive metadata
    title = models.CharField(max_length=200, validators=[validate_alphaplus])
    abstract = RichTextField(max_length=10000, blank=True)
    background = RichTextField(blank=True)
    methods = RichTextField(blank=True)
    content_description = RichTextField(blank=True)
    usage_notes = RichTextField(blank=True)
    installation = RichTextField(blank=True)
    acknowledgements = RichTextField(blank=True)
    conflicts_of_interest = RichTextField(blank=True)
    version = models.CharField(max_length=15, default='', blank=True)
    release_notes = RichTextField(blank=True)

    # Short description used for search results, social media, etc
    short_description = models.CharField(max_length=250, blank=True, 
        validators=[validate_alphaplusplus])

    # Access information
    access_policy = models.SmallIntegerField(choices=ACCESS_POLICIES,
                                             default=0)
    license = models.ForeignKey('project.License', null=True,
        on_delete=models.SET_NULL)
    project_home_page = models.URLField(default='', blank=True)
    programming_languages = models.ManyToManyField(
        'project.ProgrammingLanguage', related_name='%(class)ss')

    # Public url slug, also used as a submitting project id.
    slug = models.SlugField(max_length=20, unique=True, db_index=True)
    core_project = models.ForeignKey('project.CoreProject',
                                     related_name='%(class)ss',
                                     on_delete=models.CASCADE)

    # When the submitting project was created
    creation_datetime = models.DateTimeField(auto_now_add=True)

    edit_logs = GenericRelation('project.EditLog')
    copyedit_logs = GenericRelation('project.CopyeditLog')

    # For ordering projects with multiple versions
    version_order = models.PositiveSmallIntegerField(default=0)


    class Meta:
        abstract = True

    def author_contact_info(self, only_submitting=False):
        """
        Get the names and emails of the project's authors.
        """
        if only_submitting:
            user = self.authors.get(is_submitting=True).user
            return user.email, user.get_full_name
        else:
            users = [a.user for a in self.authors.all()]
            return ((u.email, u.get_full_name()) for u in users)

    def corresponding_author(self):
        return self.authors.get(is_corresponding=True)

    def submitting_author(self):
        return self.authors.get(is_submitting=True)

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
            if include_emails:
                return submitting_author, coauthors, author_emails
            else:
                return submitting_author, coauthors
        else:
            for a in authors:
                a.set_display_info()
            if include_emails:
                return authors, author_emails
            else:
                return authors

    def info_card(self, include_emails=True):
        """
        Get all the information needed for the project info card
        seen by an admin
        """
        authors, author_emails = self.get_author_info(include_emails=include_emails)
        storage_info = self.get_storage_info()
        edit_logs = self.edit_logs.all()
        for e in edit_logs:
            e.set_quality_assurance_results()
        copyedit_logs = self.copyedit_logs.all()
        return authors, author_emails, storage_info, edit_logs, copyedit_logs

    def license_content(self, fmt):
        """
        Get the license content of the project's license in text or html
        content. Takes the selected license and fills in the year and
        copyright holder.
        """
        author_names = ', '.join(a.get_full_name() for a in self.authors.all()) + '.'

        if fmt == 'text':
            content = self.license.text_content
            content = content.replace('<COPYRIGHT HOLDER>', author_names, 1)
            content = content.replace('<YEAR>', str(timezone.now().year), 1)
        elif fmt == 'html':
            content = self.license.html_content
            content = content.replace('&lt;COPYRIGHT HOLDER&gt;', author_names, 1)
            content = content.replace('&lt;YEAR&gt;', str(timezone.now().year), 1)

        return content


class SubmissionInfo(models.Model):
    """
    Submission information, inherited by all projects.
    """
    editor = models.ForeignKey('user.User',
        related_name='editing_%(class)ss', null=True,
        on_delete=models.SET_NULL)
    # The very first submission
    submission_datetime = models.DateTimeField(null=True)
    author_comments = models.CharField(max_length=1000, default='')
    editor_assignment_datetime = models.DateTimeField(null=True)
    # The last revision request (if any)
    revision_request_datetime = models.DateTimeField(null=True)
    # The last resubmission (if any)
    resubmission_datetime = models.DateTimeField(null=True)
    editor_accept_datetime = models.DateTimeField(null=True)
    # The last copyedit (if any)
    copyedit_completion_datetime = models.DateTimeField(null=True)
    author_approval_datetime = models.DateTimeField(null=True)

    class Meta:
        abstract = True


class UnpublishedProject(models.Model):
    """
    Abstract model inherited by ArchivedProject/ActiveProject
    """
    modified_datetime = models.DateTimeField(auto_now=True)

    authors = GenericRelation('project.Author')
    references = GenericRelation('project.Reference')
    publications = GenericRelation('project.Publication')
    topics = GenericRelation('project.Topic')

    authors = GenericRelation('project.Author')

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    def file_root(self):
        """
        Root directory containing the project's files
        """
        return os.path.join(self.__class__.FILE_ROOT, self.slug)

    def get_storage_info(self):
        """
        Return an object containing information about the project's
        storage usage.
        """
        return StorageInfo(allowance=self.core_project.storage_allowance,
            used=self.storage_used(), include_remaining=True)

    def remove(self):
        """
        Delete this project's file content and the object
        """
        shutil.rmtree(self.file_root())
        return self.delete()


class ArchivedProject(Metadata, UnpublishedProject, SubmissionInfo):
    """
    An archived project. Created when (maps to archive_reason):
    1. A user chooses to 'delete' their ActiveProject.
    2. An ActiveProject is not submitted for too long.
    3. An ActiveProject is submitted and rejected.
    4. An ActiveProject is submitted and times out.
    """
    archive_datetime = models.DateTimeField(auto_now_add=True)
    archive_reason = models.PositiveSmallIntegerField()

    # Where all the archived project files are kept
    FILE_ROOT = os.path.join(settings.MEDIA_ROOT, 'archived-projects')

    def __str__(self):
        return ('{0} v{1}'.format(self.title, self.version))


class ActiveProject(Metadata, UnpublishedProject, SubmissionInfo):
    """
    The project used for submitting

    The submission_status field:
    - 0 : Not submitted
    - 10 : Submitting author submits. Awaiting editor assignment.
    - 20 : Editor assigned. Awaiting editor decision.
    - 30 : Revisions requested. Waiting for resubmission. Loops back
          to 20 when author resubmits.
    - 40 : Accepted. In copyedit stage. Awaiting editor to copyedit.
    - 50 : Editor completes copyedit. Awaiting authors to approve.
    - 60 : Authors approve copyedit. Ready for editor to publish

    """
    submission_status = models.PositiveSmallIntegerField(default=0)

    # Max number of active submitting projects a user is allowed to have
    MAX_SUBMITTING_PROJECTS = 10
    INDIVIDUAL_FILE_SIZE_LIMIT = 10 * 1024**3
    # Where all the active project files are kept
    FILE_ROOT = os.path.join(settings.MEDIA_ROOT, 'active-projects')

    REQUIRED_FIELDS = (
        # 0: Database
        ('title', 'abstract', 'background', 'methods', 'content_description',
         'usage_notes', 'conflicts_of_interest', 'version', 'license'),
        # 1: Software
        ('title', 'abstract', 'background', 'content_description',
         'usage_notes', 'installation', 'conflicts_of_interest', 'version',
         'license'),
        # 2: Challenge
        ('title', 'abstract', 'background', 'methods', 'content_description',
         'usage_notes', 'conflicts_of_interest', 'version', 'license'),
    )

    # Custom labels that don't match model field names
    LABELS = (
        # 0: Database
        {'content_description': 'Data Description'},
        # 1: Software
        {'content_description': 'Software Description',
         'methods': 'Technical Implementation',
         'installation': 'Installation and Requirements'},
        # 2: Challenge
        {'background': 'Objective',
         'methods': 'Participation',
         'content_description': 'Data Description',
         'usage_notes': 'Evaluation'},
    )

    SUBMISSION_STATUS_LABELS = {
        0: 'Not submitted.',
        10: 'Awaiting editor assignment.',
        20: 'Awaiting editor decision.',
        30: 'Revisions requested.',
        40: 'Submission accepted; awaiting editor copyedits.',
        50: 'Awaiting authors to approve publication.',
        60: 'Awaiting editor to publish.',
    }

    def storage_used(self):
        """
        Total storage used in bytes
        """
        return get_tree_size(self.file_root())

    def storage_allowance(self):
        """
        Storage allowed in bytes
        """
        return self.core_project.storage_allowance

    def get_inspect_dir(self, subdir):
        """
        Return the folder to inspect if valid. subdir joined onto
        the file root of this project.
        """
        # Sanitize subdir for illegal characters
        validate_subdir(subdir)
        # Folder must be a subfolder of the file root and exist
        inspect_dir = os.path.join(self.file_root(), subdir)
        if inspect_dir.startswith(self.file_root()) and os.path.isdir(inspect_dir):
            return inspect_dir
        else:
            raise Exception('Invalid directory request')

    def get_directory_content(self, subdir=''):
        """
        Return information for displaying file and directories
        """
        inspect_dir = self.get_inspect_dir(subdir)
        file_names , dir_names = list_items(inspect_dir)
        display_files, display_dirs = [], []

        # Files require desciptive info and download links
        for file in file_names:
            file_info = get_file_info(os.path.join(inspect_dir, file))
            file_info.full_file_name = os.path.join(subdir, file)
            display_files.append(file_info)

        # Directories require links
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

    def submission_deadline(self):
        return self.creation_datetime + timedelta(days=180)

    def submission_days_remaining(self):
        return (self.submission_deadline() - timezone.now()).days

    def submission_status_label(self):
        return ActiveProject.SUBMISSION_STATUS_LABELS[self.submission_status]

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
        if self.submission_status == 40:
            return True

    def archive(self, archive_reason):
        """
        Archive the project. Create an ArchivedProject object, copy over
        the fields, and delete this object
        """
        archived_project = ArchivedProject(archive_reason=archive_reason)

        # Direct copy over fields
        for attr in [f.name for f in Metadata._meta.fields] + [f.name for f in SubmissionInfo._meta.fields] + ['modified_datetime']:
            setattr(archived_project, attr, getattr(self, attr))

        archived_project.save()

        # Redirect the related objects
        for reference in self.references.all():
            reference.project = archived_project
            reference.save()
        for publication in self.publications.all():
            publication.project = archived_project
            publication.save()
        for topic in self.topics.all():
            topic.project = archived_project
            topic.save()
        for author in self.authors.all():
            author.project = archived_project
            author.save()
        for edit_log in self.edit_logs.all():
            edit_log.project = archived_project
            edit_log.save()
        for copyedit_log in self.copyedit_logs.all():
            copyedit_log.project = archived_project
            copyedit_log.save()
        if self.resource_type == 1:
            languages = self.programming_languages.all()
            if languages:
                archived_project.programming_languages.add(*list(languages))

        # Voluntary delete
        if archive_reason == 1:
            self.clear_files()
        else:
            # Move over files
            os.rename(self.file_root(), archived_project.file_root())
        return self.delete()

    def fake_delete(self):
        """
        Appear to delete this project. Actually archive it.
        """
        self.archive(archive_reason=1)


    def check_integrity(self):
        """
        Run integrity tests on metadata fields and return whether the
        project passes the checks
        """
        self.integrity_errors = []

        # Invitations
        for invitation in self.authorinvitations.filter(is_active=True):
            self.integrity_errors.append(
                'Outstanding author invitation to {0}'.format(invitation.email))

        # Storage requests
        for storage_request in self.storagerequests.filter(
                is_active=True):
            self.integrity_errors.append('Outstanding storage request')

        # Authors
        for author in self.authors.all():
            if not author.get_full_name():
                self.integrity_errors.append('Author {0} has not fill in name'.format(author.user.username))
            if not author.affiliations.all():
                self.integrity_errors.append('Author {0} has not filled in affiliations'.format(author.user.username))

        # Metadata
        for attr in ActiveProject.REQUIRED_FIELDS[self.resource_type]:
            if not getattr(self, attr):
                l = self.LABELS[self.resource_type][attr] if attr in self.LABELS[self.resource_type] else attr.title().replace('_', ' ')
                self.integrity_errors.append('Missing required field: {0}'.format(l))

        published_projects = self.core_project.publishedprojects.all()
        if published_projects:
            published_versions = [p.version for p in published_projects]
            if self.version in published_versions:
                self.integrity_errors.append('The version matches a previously published version.')
                self.version_clash = True
            else:
                self.version_clash = False

        if self.integrity_errors:
            return False
        else:
            return True

    def is_submittable(self):
        """
        Whether the project can be submitted
        """
        return (not self.under_submission() and self.check_integrity())

    def submit(self, author_comments):
        """
        Submit the project for review.
        """
        if not self.is_submittable():
            raise Exception('ActiveProject is not submittable')

        self.submission_status = 10
        self.submission_datetime = timezone.now()
        self.author_comments = author_comments
        self.save()
        # Create the first edit log
        EditLog.objects.create(project=self, author_comments=author_comments)

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
        self.editor_assignment_datetime = timezone.now()
        self.save()

    def reject(self):
        """
        Reject a project under submission
        """
        self.archive(archive_reason=3)

    def is_resubmittable(self):
        """
        Submit the project for review.
        """
        return (self.submission_status == 30 and self.check_integrity())

    def resubmit(self, author_comments):
        """
        """
        if not self.is_resubmittable():
            raise Exception('ActiveProject is not resubmittable')

        self.submission_status = 20
        self.resubmission_datetime = timezone.now()
        self.save()
        # Create a new edit log
        EditLog.objects.create(project=self, is_resubmission=True,
            author_comments=author_comments)

    def reopen_copyedit(self):
        """
        Reopen the project for copyediting
        """
        if self.submission_status == 50:
            self.submission_status = 40
            self.copyedit_completion_datetime = None
            self.save()
            CopyeditLog.objects.create(project=self, is_reedit=True)
            self.authors.all().update(approval_datetime=None)

    def approve_author(self, author):
        """"
        Approve an author. Move the project into the next state if the
        author is the final outstanding one. Return whether the
        process was successful.
        """
        if self.submission_status == 50 and not author.approval_datetime:
            now = timezone.now()
            author.approval_datetime = now
            author.save()
            if self.all_authors_approved():
                self.author_approval_datetime = now
                self.submission_status = 60
                self.save()
            return True

    def all_authors_approved(self):
        """
        Whether all authors have approved the publication
        """
        authors = self.authors.all()
        return len(authors) == len(authors.filter(
            approval_datetime__isnull=False))

    def is_publishable(self):
        """
        Check whether a project may be published
        """
        if self.submission_status == 60 and self.check_integrity() and self.all_authors_approved():
            return True
        return False

    def clear_files(self):
        """
        Delete the project file directory
        """
        shutil.rmtree(self.file_root())

    def publish(self, doi, slug=None, make_zip=True):
        """
        Create a published version of this project and update the
        submission status.

        Parameters
        ----------
        doi : the desired doi of the published project.
        slug : the desired custom slug of the published project.
        make_zip : whether to make a zip of all the files.
        """
        if not self.is_publishable():
            raise Exception('The project is not publishable')

        published_project = PublishedProject(doi=doi)

        # Direct copy over fields
        for attr in [f.name for f in Metadata._meta.fields] + [f.name for f in SubmissionInfo._meta.fields]:
            setattr(published_project, attr, getattr(self, attr))

        # Set the slug if specified
        published_project.slug = slug or self.slug
        published_project.save()

        # Same content, different objects.
        for reference in self.references.all():
            published_reference = PublishedReference.objects.create(
                description=reference.description,
                project=published_project)

        for publication in self.publications.all():
            published_publication = PublishedPublication.objects.create(
                citation=publication.citation, url=publication.url,
                project=published_project)

        for topic in self.topics.all():
            published_topic = PublishedTopic.objects.filter(
                description=topic.description.lower())
            # Tag the published project with the topic. Create the published
            # topic first if it doesn't exist
            if published_topic.count():
                published_topic = published_topic.get()
            else:
                published_topic = PublishedTopic.objects.create(
                    description=topic.description.lower())
            published_topic.projects.add(published_project)
            published_topic.project_count += 1
            published_topic.save()

        if self.resource_type == 1:
            languages = self.programming_languages.all()
            if languages:
                published_project.programming_languages.add(*list(languages))

        for author in self.authors.all():
            author_profile = author.user.profile
            published_author = PublishedAuthor.objects.create(
                project=published_project, user=author.user,
                is_submitting=author.is_submitting,
                is_corresponding=author.is_corresponding,
                approval_datetime=author.approval_datetime,
                display_order=author.display_order,
                first_names=author_profile.first_names,
                last_name=author_profile.last_name,
                )

            affiliations = author.affiliations.all()
            for affiliation in affiliations:
                published_affiliation = PublishedAffiliation.objects.create(
                    name=affiliation.name, author=published_author)

            if author.is_corresponding:
                published_author.corresponding_email = author.corresponding_email.email
                published_author.save()
                contact = Contact.objects.create(name=author.get_full_name(),
                affiliations='; '.join(a.name for a in affiliations),
                email=author.corresponding_email, project=published_project)

        # Move the edit and copyedit logs
        for edit_log in self.edit_logs.all():
            edit_log.project = published_project
            edit_log.save()
        for copyedit_log in self.copyedit_logs.all():
            copyedit_log.project = published_project
            copyedit_log.save()

        # Create file root
        os.mkdir(published_project.file_root())
        # Move over main files
        os.rename(self.file_root(), published_project.main_file_root())
        # Create special files if there are files. Should always be the case.
        if bool(self.storage_used):
            published_project.make_special_files(make_zip=make_zip)
        published_project.set_storage_info()
        # Remove the ActiveProject
        self.delete()

        return published_project


class PublishedProject(Metadata, SubmissionInfo):
    """
    A published project. Immutable snapshot.

    """
    # File storage sizes in bytes
    main_storage_size = models.BigIntegerField(default=0)
    compressed_storage_size = models.BigIntegerField(default=0)
    publish_datetime = models.DateTimeField(auto_now_add=True)
    is_newest_version = models.BooleanField(default=True)
    newest_version = models.ForeignKey('project.PublishedProject', null=True,
        related_name='older_versions', on_delete=models.SET_NULL)
    # doi = models.CharField(max_length=50, unique=True, validators=[validate_doi])
    # Temporary workaround
    doi = models.CharField(max_length=50, default='')
    approved_users = models.ManyToManyField('user.User', db_index=True)
    # Fields for legacy pb databases
    is_legacy = models.BooleanField(default=False)
    full_description = RichTextField(default='')

    # Where all the published project files are kept, depending on access.
    PROTECTED_FILE_ROOT = os.path.join(settings.MEDIA_ROOT, 'published-projects')
    # Workaround for development
    if os.environ['DJANGO_SETTINGS_MODULE'] == 'physionet.settings.development':
        PUBLIC_FILE_ROOT = os.path.join(settings.STATICFILES_DIRS[0], 'published-projects')
    else:
        PUBLIC_FILE_ROOT = os.path.join(settings.STATIC_ROOT, 'published-projects')

    SPECIAL_FILES = {
        'FILES.txt':'List of all files',
        'LICENSE.txt':'License for using files',
        'SHA256SUMS.txt':'Checksums of all files',
        'RECORDS.txt':'List of WFDB format records',
        'ANNOTATORS.tsv':'List of WFDB annotation file types'
    }

    class Meta:
        unique_together = (('core_project', 'version'),)

    def __str__(self):
        return ('{0} v{1}'.format(self.title, self.version))

    def file_root(self):
        """
        Root directory containing the published project's files.

        This is the parent directory of the main and special file
        directories.
        """
        if self.access_policy:
            return os.path.join(PublishedProject.PROTECTED_FILE_ROOT, self.slug)
        else:
            return os.path.join(PublishedProject.PUBLIC_FILE_ROOT, self.slug)

    def main_file_root(self):
        """
        Root directory where the main user uploaded files are located
        """
        return os.path.join(self.file_root(), 'files')

    def storage_used(self):
        """
        Bytes of storage used by main files and compressed file if any
        """
        main = get_tree_size(self.main_file_root())
        compressed = os.path.getsize(self.zip_name(full=True)) if os.path.isfile(self.zip_name(full=True)) else 0
        return main, compressed

    def set_storage_info(self):
        """
        Sum up the file sizes of the project and set the storage info
        fields
        """
        self.main_storage_size, self.compressed_storage_size = self.storage_used()
        self.save()

    def slugged_label(self):
        """
        Slugged readable label from the title and version. Used for
        the project's zipped files
        """
        return '-'.join((slugify(self.title), self.version.replace(' ', '-')))

    def zip_name(self, full=False):
        """
        Name of the zip file. Either base name or full path name.
        """
        name = '{}.zip'.format(self.slugged_label())
        if full:
            name = os.path.join(self.file_root(), name)
        return name

    def make_zip(self):
        """
        Make a (new) zip file of the main files.
        """
        # Where the zip should be
        fname = self.zip_name(full=True)
        if os.path.isfile(fname):
            os.remove(fname)

        # Prevent recursively zipping the zip file
        zipfile = shutil.make_archive(base_name=os.path.join(
            PublishedProject.PROTECTED_FILE_ROOT, self.slugged_label()),
            format='zip', root_dir=self.file_root())

        os.rename(zipfile, fname)
        self.compressed_storage_size = os.path.getsize(fname)
        self.save()

    def zip_url(self):
        """
        The url to download the zip file from. Only needed for open
        projects
        """
        if self.access_policy:
            raise Exception('This should not be called by protected projects')
        else:
            return os.path.join('published-projects', self.slug, self.zip_name())

    def make_checksum_file(self):
        """
        Make the checksums file for the main files
        """
        fname = os.path.join(self.main_file_root(), 'SHA256SUMS.txt')
        if os.path.isfile(fname):
            os.remove(fname)

        files = get_tree_files(self.main_file_root(), full_path=False)
        with open(fname, 'w') as outfile:
            for f in files:
                outfile.write('{} {}\n'.format(
                    hashlib.sha256(open(os.path.join(self.main_file_root(), f), 'rb').read()).hexdigest(), f))

        self.set_storage_info()

    def make_license_file(self):
        """
        Make the license text file
        """
        with open(os.path.join(self.main_file_root(), 'LICENSE.txt'), 'w') as outfile:
            outfile.write(self.license_content(fmt='text'))

        self.set_storage_info()

    def make_special_files(self, make_zip):
        """
        Make the special files for the database. zip file, files list,
        checksum.
        """
        self.make_license_file()
        self.make_checksum_file()
        # This should come last since it also zips the special files
        if make_zip:
            self.make_zip()

    def get_inspect_dir(self, subdir):
        """
        Return the folder to inspect if valid. subdir joined onto the
        main file root of this project.
        """
        # Sanitize subdir for illegal characters
        validate_subdir(subdir)
        # Folder must be a subfolder of the file root and exist
        inspect_dir = os.path.join(self.main_file_root(), subdir)
        if inspect_dir.startswith(self.main_file_root()) and os.path.isdir(inspect_dir):
            return inspect_dir
        else:
            raise Exception('Invalid directory request')

    def get_main_directory_content(self, subdir=''):
        """
        Return information for displaying files and directories from
        the main file root
        """
        # Get folder to inspect if valid
        inspect_dir = self.get_inspect_dir(subdir)
        file_names , dir_names = list_items(inspect_dir)
        display_files, display_dirs = [], []

        # Files require desciptive info and download links
        for file in file_names:
            file_info = get_file_info(os.path.join(inspect_dir, file))
            if self.access_policy:
                file_info.full_file_name = os.path.join('files', subdir, file)
            else:
                file_info.static_url = os.path.join('published-projects', str(self.slug), 'files', subdir, file)
            display_files.append(file_info)
        # Directories require links
        for dir_name in dir_names:
            dir_info = get_directory_info(os.path.join(inspect_dir, dir_name))
            dir_info.full_subdir = os.path.join(subdir, dir_name)
            display_dirs.append(dir_info)

        return display_files, display_dirs

    def has_access(self, user):
        """
        Whether the user has access to this project
        """
        if self.access_policy:
            if self.approved_users.filter(id=user.id):
                return True
            else:
                return False
        else:
            return True

    def get_storage_info(self):
        """
        Return an object containing information about the project's
        storage usage. Main, compressed, total files, and allowance.
        """
        main, compressed = self.storage_used()
        return StorageInfo(allowance=self.core_project.storage_allowance,
            used=main+compressed, include_remaining=False, main_used=main,
            compressed_used=compressed)

    def citation_text(self):
        if self.is_legacy:
            return ''
        # Temporary workaround
        # return '{} ({}). {}. PhysioNet. doi:{}'.format(
        #     ', '.join(a.initialed_name() for a in self.authors.all()),
        #     self.publish_datetime.year, self.title, self.doi)
        return '{} ({}). {}. PhysioNet.'.format(
            ', '.join(a.initialed_name() for a in self.authors.all()),
            self.publish_datetime.year, self.title)

    def remove(self, force=False):
        """
        Remove the project and its files. Probably will never be used
        in production. `force` argument is for safety.

        """
        if force:
            shutil.rmtree(self.file_root())
            return self.delete()
        else:
            raise Exception('Make sure you want to remove this item.')


def exists_project_slug(slug):
    """
    Whether the slug has been taken by an existing project of any
    kind.
    """
    return bool(ActiveProject.objects.filter(slug=slug)
            or ArchivedProject.objects.filter(slug=slug)
            or PublishedProject.objects.filter(slug=slug))


class ProgrammingLanguage(models.Model):
    """
    Language to tag all projects
    """
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class License(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    text_content = models.TextField(default='')
    html_content = RichTextField(default='')
    home_page = models.URLField()
    # A project must choose a license with a matching access policy and
    # resource type
    access_policy = models.PositiveSmallIntegerField(choices=Metadata.ACCESS_POLICIES,
        default=0)
    resource_type = models.PositiveSmallIntegerField(choices=Metadata.RESOURCE_TYPES)
    # A protected license has associated DUA content
    dua_name = models.CharField(max_length=100, blank=True, default='')
    dua_html_content = RichTextField(blank=True, default='')

    def __str__(self):
        return self.name


class DUASignature(models.Model):
    """
    Log of user signing DUA
    """
    project = models.ForeignKey('project.PublishedProject',
        on_delete=models.CASCADE)
    user = models.ForeignKey('user.User', on_delete=models.CASCADE)
    sign_datetime = models.DateTimeField(auto_now_add=True)


class BaseInvitation(models.Model):
    """
    Base class for authorship invitations and storage requests
    """
    project = models.ForeignKey('project.ActiveProject',
        related_name='%(class)ss', on_delete=models.CASCADE)
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
    inviter = models.ForeignKey('user.User', on_delete=models.CASCADE)

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
    # Requested storage size in GB. Max = 10Tb
    request_allowance = models.SmallIntegerField(
        validators=[MaxValueValidator(10240), MinValueValidator(1)])
    responder = models.ForeignKey('user.User', null=True,
        on_delete=models.SET_NULL)
    response_message = models.CharField(max_length=50, default='', blank=True)

    def __str__(self):
        return '{0}GB for project: {1}'.format(self.request_allowance,
                                               self.project.__str__())


class EditLog(models.Model):
    """
    Log for an editor decision. Also saves submission info.
    """
    # Quality assurance fields for data and software
    QUALITY_ASSURANCE_FIELDS = (
        # 0: Database
        ('soundly_produced', 'well_described', 'open_format',
         'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable'),
        # 1: Software
        ('well_described', 'open_format', 'reusable', 'pn_suitable'),
        # 2: Challenge
        ('soundly_produced', 'well_described', 'open_format',
         'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable'),
    )
    # The editor's free input fields
    EDITOR_FIELDS = ('editor_comments', 'decision')

    COMMON_LABELS = {
        'reusable':'Does the project include everything needed for reuse by the community?',
        'pn_suitable':'Is the content suitable for PhysioNet?',
        'editor_comments':'Comments to authors',
    }

    LABELS = (
        # 0: Database
        {'soundly_produced':'Has the data been produced in a sound manner?',
         'well_described':'Is the data adequately described?',
         'open_format':'Is the data provided in an open format?',
         'data_machine_readable':'Are the data files machine-readable?',
         'no_phi':'Is the data free of protected health information?'},
        # 1: Software
        {'well_described':'Is the software adequately described?',
         'open_format':'Is the software provided in an open format?'},
        # 2: Challenge
        {'soundly_produced':'Has the challenge been produced in a sound manner?',
         'well_described':'Is the challenge adequately described?',
         'open_format':'Is all content provided in an open format?',
         'data_machine_readable':'Are all files machine-readable?',
         'no_phi':'Is the content free of protected health information?'},
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    # When the submitting author submits/resubmits
    submission_datetime = models.DateTimeField(auto_now_add=True)
    is_resubmission = models.BooleanField(default=False)
    author_comments = models.CharField(max_length=1000, default='')
    # Quality assurance fields
    soundly_produced = models.NullBooleanField(null=True)
    well_described = models.NullBooleanField(null=True)
    open_format = models.NullBooleanField(null=True)
    data_machine_readable = models.NullBooleanField(null=True)
    reusable = models.NullBooleanField(null=True)
    no_phi = models.NullBooleanField(null=True)
    pn_suitable = models.NullBooleanField(null=True)
    # Editor decision. 0 1 2 for reject/revise/accept
    decision = models.SmallIntegerField(null=True)
    decision_datetime = models.DateTimeField(null=True)
    # Comments for the decision
    editor_comments = models.CharField(max_length=2500)

    def set_quality_assurance_results(self):
        """
        Prepare the string fields for the editor's decisions of the
        quality assurance fields, to be displayed. Does nothing if the
        decision has not been made.
        """
        if not self.decision_datetime:
            return

        resource_type = self.project.resource_type
        NO_YES = ('No', 'Yes')
        # The quality assurance fields we want.
        # Retrieve their labels and results.
        quality_assurance_fields = self.__class__.QUALITY_ASSURANCE_FIELDS[resource_type]
        # Create the labels dictionary for this resource type
        labels = {**self.__class__.COMMON_LABELS, **self.__class__.LABELS[resource_type]}

        self.quality_assurance_results = ['{}: {}'.format(
            labels[f], NO_YES[getattr(self, f)]) for f in quality_assurance_fields]


class CopyeditLog(models.Model):
    """
    Log for an editor copyedit
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')
    # Either the time the project was accepted and moved into copyedit
    # from the edit stage, or the time it was reopened for copyedit from
    # the author approval stage.
    start_datetime = models.DateTimeField(auto_now_add=True)
    # Whether the submission was reopened for copyediting
    is_reedit = models.BooleanField(default=False)
    made_changes = models.NullBooleanField(null=True)
    changelog_summary = models.CharField(default='', max_length=2500, blank=True)
    complete_datetime = models.DateTimeField(null=True)


class LegacyProject(models.Model):
    """
    Temporary model for migrating legacy databases
    """
    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=100)
    abstract = RichTextField(blank=True, default='')
    full_description = RichTextField()
    doi = models.CharField(max_length=100, blank=True, default='')
    version = models.CharField(max_length=20, default='1.0.0')

    resource_type = models.PositiveSmallIntegerField(default=0)
    publish_date = models.DateField()

    # In case we want a citation
    citation = models.CharField(blank=True, default='', max_length=1000)
    citation_url = models.URLField(blank=True, default='')

    contact_name = models.CharField(max_length=120, default='PhysioNet Support')
    contact_affiliations = models.CharField(max_length=150, default='MIT')
    contact_email = models.EmailField(max_length=255, default='webmaster@physionet.org')

    # Put the references as part of the full description

    def __str__(self):
        return ' --- '.join([self.slug, self.title])

    def publish(self, make_file_roots=False):
        """
        Turn into a published project
        """
        p = PublishedProject.objects.create(title=self.title,
            doi=self.doi, slug=self.slug,
            resource_type=self.resource_type,
            core_project=CoreProject.objects.create(),
            abstract=self.abstract,
            is_legacy=True, full_description=self.full_description,
            version=self.version,
            license=License.objects.get(name='Open Data Commons Attribution License v1.0')
        )

        # Have to set publish_datetime here due to auto_now_add of object
        dt = datetime.combine(self.publish_date, datetime.min.time())
        dt = pytz.timezone(timezone.get_default_timezone_name()).localize(dt)
        p.publish_datetime = dt
        p.save()

        # Related objects
        if self.citation:
            PublishedPublication.objects.create(citation=self.citation,
                url=self.citation_url, project=p)

        Contact.objects.create(name=self.contact_name,
            affiliations=self.contact_affiliations, email=self.contact_email,
            project=p)

        if make_file_roots:
            os.mkdir(p.file_root())
            os.mkdir(p.main_file_root())
