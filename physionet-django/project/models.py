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
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from .utility import get_tree_size, get_file_info, get_directory_info, list_items, get_storage_info


class Affiliation(models.Model):
    """
    Affiliations belonging to an author

    """
    name = models.CharField(max_length=202)
    author = models.ForeignKey('project.Author', related_name='affiliations')

    class Meta:
        unique_together = (('name', 'author'),)


class PublishedAffiliation(models.Model):
    "Affiliations belonging to a published author"
    name = models.CharField(max_length=202)
    author = models.ForeignKey('project.PublishedAuthor',
        related_name='affiliations')

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
    corresponding_email = models.ForeignKey('user.AssociatedEmail', null=True)

    class Meta:
        unique_together = (('user', 'content_type', 'object_id',),)

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
        self.name = user.profile.get_full_name()
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

    project = models.ForeignKey('project.PublishedProject',
        related_name='authors', db_index=True)

    class Meta:
        unique_together = (('user', 'project'),)

    def get_full_name(self):
        if self.middle_names:
            return ' '.join([self.first_name, self.middle_names,
                           self.last_name])
        else:
            return ' '.join([self.first_name, self.last_name])

    def set_display_info(self):
        """
        Set the fields used to display the author
        """
        self.name = self.get_full_name()
        self.username = self.user.username
        self.text_affiliations = [a.name for a in self.affiliations.all()]



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
    projects = models.ManyToManyField('project.PublishedProject',
        related_name='topics')
    description = models.CharField(max_length=50)

    def __str__(self):
        return self.description


class Reference(models.Model):
    """
    Reference field for ActiveProject/ArchivedProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    description = models.CharField(max_length=250)

    class Meta:
        unique_together = (('description', 'content_type', 'object_id'),)

    def __str__(self):
        return self.description


class PublishedReference(models.Model):
    description = models.CharField(max_length=250)
    project = models.ForeignKey('project.PublishedProject',
        related_name='references')

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
    project = models.ForeignKey('project.PublishedProject',
        db_index=True, related_name='publications')


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
    acknowledgements = RichTextField(blank=True)
    conflicts_of_interest = RichTextField(blank=True)
    version = models.CharField(max_length=15, default='', blank=True)
    changelog_summary = RichTextField(blank=True)
    # Access information
    access_policy = models.SmallIntegerField(choices=ACCESS_POLICIES,
                                             default=0)
    license = models.ForeignKey('project.License', null=True)
    data_use_agreement = models.ForeignKey('project.DataUseAgreement',
                                           null=True, blank=True)
    # Public url slug, also used as a submitting project id.
    slug = models.SlugField(max_length=20, unique=True, db_index=True)
    core_project = models.ForeignKey('project.CoreProject',
                                     related_name='%(class)ss')
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

    def get_storage_info(self):
        """
        Return an object containing information about the project's
        storage usage.
        """
        return get_storage_info(allowance=self.core_project.storage_allowance,
            used=self.storage_used())


class SubmissionInfo(models.Model):
    """
    Submission information, inherited by all projects.
    """
    editor = models.ForeignKey('user.User',
        related_name='editing_%(class)ss', null=True)
    # The very first submission
    submission_datetime = models.DateTimeField(null=True)
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

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    def file_root(self):
        "Root directory containing the project's files"
        return os.path.join(self.__class__.FILE_ROOT, self.slug)


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

    INDIVIDUAL_FILE_SIZE_LIMIT = 10 * 1024**3
    # Where all the active project files are kept
    FILE_ROOT = os.path.join(settings.MEDIA_ROOT, 'active-projects')

    REQUIRED_FIELDS = {0:['title', 'abstract', 'background', 'methods',
                          'content_description', 'conflicts_of_interest',
                          'version', 'license',],
                       1:['title', 'abstract', 'background', 'methods',
                          'content_description', 'conflicts_of_interest',
                          'version', 'license',]}

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

    def archive(self, archive_reason):
        """
        Archive the project. Create an ArchivedProject object, copy over
        the fields, and delete this object
        """
        archived_project = ArchivedProject(archive_reason=archive_reason)

        # Direct copy over fields
        for attr in [
                # Management fields
                'core_project', 'slug',
                # Metadata info
                'resource_type', 'title', 'abstract', 'background', 'methods',
                'content_description', 'usage_notes', 'acknowledgements',
                'conflicts_of_interest', 'version', 'access_policy',
                'changelog_summary', 'access_policy', 'license',
                # Publishing info
                'editor', 'creation_datetime', 'submission_datetime',
                'editor_assignment_datetime', 'editor_accept_datetime',
                'copyedit_completion_datetime', 'author_approval_datetime',
                'version_order']:
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

        # Move over files
        os.rename(self.file_root(), archived_project.file_root())
        return self.delete()

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
                self.integrity_errors.append('Missing required field: {0}'.format(attr.replace('_', ' ')))

        if self.access_policy and not self.data_use_agreement:
            self.integrity_errors.append('Missing DUA for non-open access policy')

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
        "Whether the project can be submitted"
        return (not self.under_submission() and self.check_integrity())

    def submit(self):
        """
        Submit the project for review.
        """
        if not self.is_submittable():
            raise Exception('ActiveProject is not submittable')

        self.submission_status = 10
        self.submission_datetime = timezone.now()
        self.save()
        # Create the first edit log
        EditLog.objects.create(project=self)

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
        "Reject a project under submission"
        self.archive(archive_reason=3)

    def is_resubmittable(self):
        """
        Submit the project for review.
        """
        return (self.submission_status == 30 and self.check_integrity())

    def resubmit(self):
        if not self.is_resubmittable():
            raise Exception('ActiveProject is not resubmittable')

        self.submission_status = 20
        self.resubmission_datetime = timezone.now()
        self.save()
        # Create a new edit log
        EditLog.objects.create(project=self, is_resubmission=True)

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
        "Whether all authors have approved the publication"
        authors = self.authors.all()
        return len(authors) == len(authors.filter(
            approval_datetime__isnull=False))

    def info_card(self):
        """
        Get all the information needed for the submission info card
        seen by an admin/editor
        """
        authors, author_emails = self.get_author_info(include_emails=True)
        storage_info = self.get_storage_info()
        edit_logs = self.edit_logs.all()
        for e in edit_logs:
            e.set_quality_assurance_results()
        copyedit_logs = self.copyedit_logs.all()
        return authors, author_emails, storage_info, edit_logs, copyedit_logs

    def is_publishable(self):
        """
        Check whether a project may be published
        """
        if self.submission_status == 60 and self.check_integrity() and self.all_authors_approved():
            return True
        return False

    def cleanup_files(self):
        """
        Delete the project file directory
        """
        shutil.rmtree(self.file_root())

    def publish(self, make_zip=True):
        """
        Create a published version of this project and update the
        submission status
        """
        if not self.is_publishable():
            raise Exception('The project is not publishable')

        published_project = PublishedProject()

        # Direct copy over fields
        for attr in [
                # Management fields
                'core_project',
                # Metadata info
                'resource_type', 'title', 'abstract', 'background', 'methods',
                'content_description', 'usage_notes', 'acknowledgements',
                'conflicts_of_interest', 'version', 'access_policy',
                'changelog_summary', 'access_policy', 'license',
                # Publishing info
                'editor', 'creation_datetime', 'submission_datetime',
                'editor_assignment_datetime', 'editor_accept_datetime',
                'copyedit_completion_datetime', 'author_approval_datetime',
                'version_order']:
            setattr(published_project, attr, getattr(self, attr))

        # New fields
        published_project.storage_size = self.storage_used()
        # Generate a new slug
        slug = get_random_string(20)
        while PublishedProject.objects.filter(slug=slug):
            slug = get_random_string(20)
        published_project.slug = slug
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

        for author in self.authors.all():
            author_profile = author.user.profile
            published_author = PublishedAuthor.objects.create(
                project=published_project, user=author.user,
                is_submitting=author.is_submitting,
                is_corresponding=author.is_corresponding,
                approval_datetime=author.approval_datetime,
                display_order=author.display_order,
                first_name=author_profile.first_name,
                middle_names=author_profile.middle_names,
                last_name=author_profile.last_name,
                )

            affiliations = author.affiliations.all()
            for affiliation in affiliations:
                published_affiliation = PublishedAffiliation.objects.create(
                    name=affiliation.name, author=published_author)

            if author.is_corresponding:
                contact = Contact.objects.create(name=author.get_full_name(),
                affiliations=';'.join(a.name for a in affiliations),
                email=author.corresponding_email, project=published_project)

        # Non-open access policy
        # if self.access_policy:
        #     access_system = AccessSystem.objects.create(
        #         name=published_project.__str__(),
        #         license=self.license,
        #         data_use_agreement=self.data_use_agreement,
        #         requires_credentialed=bool(self.access_policy-1)
        #         )
        #     published_project.access_system = access_system
        #     published_project.save()

        # Move the edit and copyedit logs
        for edit_log in self.edit_logs.all():
            edit_log.project = published_project
            edit_log.save()
        for copyedit_log in self.copyedit_logs.all():
            copyedit_log.project = published_project
            copyedit_log.save()

        # Create file root
        os.mkdir(published_project.file_root())
        # Move over files
        os.rename(self.file_root(), published_project.main_file_root())
        # Create zip
        if make_zip:
            # The zip name is made from the title and the version
            # Rename the 'files' directory temporarily for the zip file
            zip_name = published_project.zip_file(include_extension=False,
                full_path=True)
            os.rename(published_project.main_file_root(), zip_name)
            shutil.make_archive(
                base_name=zip_name, format='zip',
                root_dir=published_project.file_root(),
                base_dir=published_project.slugged_label())
            # Change the directory name back to 'files'
            os.rename(zip_name, published_project.main_file_root())

        # Remove the ActiveProject
        self.delete()

        return published_project


class PublishedProject(Metadata, SubmissionInfo):
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

    # Where all the published project files are kept, depending on access.
    PROTECTED_FILE_ROOT = os.path.join(settings.MEDIA_ROOT, 'published-projects')
    # Workaround for development
    if os.environ['DJANGO_SETTINGS_MODULE'] == 'physionet.settings.development':
        PUBLIC_FILE_ROOT = os.path.join(settings.STATICFILES_DIRS[0], 'published-projects')
    else:
        PUBLIC_FILE_ROOT = os.path.join(settings.STATIC_ROOT, 'published-projects')

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
        """
        Root directory containing the published project's files.

        This is the parent directory of the main files, and also
        contains the zip and checksum of the main files.
        """
        if self.access_policy:
            return os.path.join(PublishedProject.PROTECTED_FILE_ROOT, self.slug)
        else:
            return os.path.join(PublishedProject.PUBLIC_FILE_ROOT, self.slug)

    def main_file_root(self):
        "Root directory where the main user uploaded files are located"
        return os.path.join(self.file_root(), 'files')

    def slugged_label(self):
        """
        Slugged readable label from the title and version. Used for
        the project's zipped files
        """
        return '-'.join((slugify(self.title), self.version.replace(' ', '-')))

    def zip_file(self, include_extension=True, full_path=False):
        """
        Name of the zip of the project's files.
        With or without .zip extension and full path.
        """
        file_name = self.slugged_label()

        if include_extension:
            file_name = '.'.join(file_name, 'zip')
        if full_path:
            file_name = os.path.join(self.file_root(), file_name)
        return file_name

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
                file_info.static_url = os.path.join('published-projects', str(self.slug), subdir, file)
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
    # Requested storage size in GB. Max = 10Tb
    request_allowance = models.SmallIntegerField(
        validators=[MaxValueValidator(10240), MinValueValidator(1)])
    responder = models.ForeignKey('user.User', null=True)
    response_message = models.CharField(max_length=50, default='', blank=True)

    def __str__(self):
        return '{0}GB for project: {1}'.format(self.request_allowance,
                                               self.project.__str__())


class EditLog(models.Model):
    """
    Log for an editor decision

    """
    # Quality assurance fields for data and software
    QUALITY_ASSURANCE_FIELDS = (
        ('soundly_produced', 'well_described', 'open_format',
        'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable'),
        (),
    )
    # The editor's free input fields
    EDITOR_FIELDS = ('editor_comments', 'decision')

    labels = {
        'soundly_produced':'The data is produced in a sound manner',
        'well_described':'The data is adequately described',
        'open_format':'The data files are provided in an open format',
        'data_machine_readable':'The data files are machine readable',
        'reusable':'All the information needed for reuse is present',
        'no_phi':'No protected health information is contained',
        'pn_suitable':'The content is suitable for PhysioNet',
        'editor_comments':'Comments to authors',
    }

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    # When the submitting author submits/resubmits
    submission_datetime = models.DateTimeField(auto_now_add=True)
    is_resubmission = models.BooleanField(default=False)
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

        NO_YES = ('No', 'Yes')

        quality_assurance_fields = self.__class__.QUALITY_ASSURANCE_FIELDS[self.project.resource_type]
        self.quality_assurance_results = ('{}: {}'.format(
            self.__class__.labels[f], NO_YES[getattr(self, f)]) for f in quality_assurance_fields)


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
