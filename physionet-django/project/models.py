from datetime import datetime, timedelta
from html import unescape
import os
import shutil
import pytz
import logging

from background_task import background
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.forms.utils import ErrorList
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from project.modelcomponents.authors import *
from project.modelcomponents.access import *
from project.modelcomponents.coreproject import *
from project.modelcomponents.fields import *
from project.modelcomponents.generic import *
from project.modelcomponents.metadata import *
from project.modelcomponents.publishedproject import *
from project.modelcomponents.submission import *
from project.modelcomponents.storage import *
from project.utility import StorageInfo
from project.validators import validate_subdir, MAX_PROJECT_SLUG_LENGTH, validate_topic


LOGGER = logging.getLogger(__name__)

@background()
def move_files_as_readonly(pid, make_zip):
    """
    Schedule a background task to set the files as read only.
    If a file starts with a Shebang, then it will be set as executable.
    """

    published_project = PublishedProject.objects.get(id=pid)

    published_project.make_checksum_file()

    quota = published_project.quota_manager()
    published_project.incremental_storage_size = quota.bytes_used
    published_project.save(update_fields=['incremental_storage_size'])

    published_project.set_storage_info()

    # Make the files read only
    file_root = published_project.project_file_root()
    for root, dirs, files in os.walk(file_root):
        for f in files:
            fline = open(os.path.join(root, f), 'rb').read(2)
            if fline[:2] == b'#!':
                os.chmod(os.path.join(root, f), 0o555)
            else:
                os.chmod(os.path.join(root, f), 0o444)

        for d in dirs:
            os.chmod(os.path.join(root, d), 0o555)

    if make_zip:
        published_project.make_zip()

class UnpublishedProject(models.Model):
    """
    Abstract model inherited by ArchivedProject/ActiveProject
    """

    # Date and time that the project's content was modified.
    # See content_modified() and save().
    modified_datetime = models.DateTimeField(auto_now=True)

    # Whether this project is being worked on as a new version
    is_new_version = models.BooleanField(default=False)
    # Access url slug, also used as a submitting project id.
    slug = models.SlugField(max_length=MAX_PROJECT_SLUG_LENGTH, db_index=True)
    latest_reminder = models.DateTimeField(null=True, blank=True)
    doi = models.CharField(max_length=50, blank=True, null=True)
    authors = GenericRelation('project.Author')
    references = GenericRelation('project.Reference')
    publications = GenericRelation('project.Publication')
    topics = GenericRelation('project.Topic')


    class Meta:
        abstract = True

    def __str__(self):
        return self.title

    def is_published(self):
        return False

    def file_root(self):
        """
        Root directory containing the project's files
        """
        return os.path.join(self.__class__.FILE_ROOT, self.slug)

    def get_storage_info(self, force_calculate=True):
        """
        Return an object containing information about the project's
        storage usage.

        If force_calculate is true, calculate the size by recursively
        scanning the directory tree.  This is deprecated.
        """
        if force_calculate:
            used = self.storage_used()
        else:
            used = None
        allowance = self.core_project.storage_allowance
        published = self.core_project.total_published_size
        return StorageInfo(allowance=allowance, published=published, used=used)

    def get_previous_slug(self):
        """
        If this is a new version of a project, get the slug of the
        published versions.
        """
        if self.version_order:
            return self.core_project.publishedprojects.all().get(
                version_order=0).slug
        else:
            raise Exception('Not a new version')


    def remove(self):
        """
        Delete this project's file content and the object
        """
        shutil.rmtree(self.file_root())
        return self.delete()

    def has_wfdb(self):
        """
        Whether the project has wfdb files.
        """
        return os.path.isfile(os.path.join(self.file_root(), 'RECORDS'))

    def content_modified(self):
        """
        Update the project's modification timestamp.

        The modification timestamp (modified_datetime) is
        automatically updated when the object is saved, if any of the
        project's Metadata fields have been modified (see
        UnpublishedProject.save).

        This function should be called when saving or deleting
        objects, other than the UnpublishedProject itself, that are
        part of the project's visible content.
        """

        # Note: modified_datetime is an auto_now field, so it is
        # automatically set to the current time whenever it is saved.
        self.save(update_fields=['modified_datetime'])

    @classmethod
    def from_db(cls, *args, **kwargs):
        """
        Instantiate an object from the database.
        """
        instance = super(UnpublishedProject, cls).from_db(*args, **kwargs)

        # Save the original field values so that we can later check if
        # they have been modified.  Note that by using __dict__, this
        # will omit any deferred fields.
        instance.orig_fields = instance.__dict__.copy()
        return instance

    def save(self, *, content_modified=None,
             force_insert=False, update_fields=None, **kwargs):
        """
        Save this object to the database.

        In addition to the standard keyword arguments, this accepts an
        optional content_modified argument: if true, modified_datetime
        will be set to the current time; if false, neither
        modified_datetime nor the Metadata fields will be saved.

        If this object was loaded from the database, and none of the
        Metadata fields have been changed from their original values,
        then content_modified defaults to False.  Otherwise,
        content_modified defaults to True.
        """

        # Note: modified_datetime is an auto_now field, so it is
        # automatically set to the current time (unless we exclude it
        # using update_fields.)

        if force_insert or update_fields:
            # If force_insert is specified, then we want to insert a
            # new object, which means setting the timestamp.  If
            # update_fields is specified, then we want to update
            # precisely those fields.  In either case, use the default
            # save method.
            return super().save(force_insert=force_insert,
                                update_fields=update_fields,
                                **kwargs)

        # If content_modified is not specified, then detect
        # automatically.
        if content_modified is None:
            if hasattr(self, 'orig_fields'):
                # Check whether any of the Metadata fields have been
                # modified since the object was loaded from the database.
                for f in Metadata._meta.fields:
                    fname = f.attname
                    if fname not in self.orig_fields:
                        # If the field was initially deferred (and
                        # thus its original value is unknown), assume
                        # that it has been modified.  This is not
                        # ideal, but in general, it should be possible
                        # to avoid this by explicitly setting
                        # update_fields or content_modified whenever
                        # deferred fields are used.
                        LOGGER.warning(
                            'saving project with initially deferred fields')
                        content_modified = True
                        break
                    if self.orig_fields[fname] != getattr(self, fname):
                        content_modified = True
                        break
            else:
                # If the object was not initially created by from_db,
                # assume content has been modified.
                content_modified = True

        if content_modified:
            # If content has been modified, then save normally.
            return super().save(**kwargs)
        else:
            # If content has not been modified, then exclude all of the
            # Metadata fields as well as modified_datetime.
            fields = ({f.name for f in self._meta.fields}
                      - {f.name for f in Metadata._meta.fields}
                      - {'id', 'modified_datetime'})
            return super().save(update_fields=fields, **kwargs)


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
         'usage_notes', 'conflicts_of_interest', 'version', 'license',
         'short_description'),
        # 1: Software
        ('title', 'abstract', 'background', 'content_description',
         'usage_notes', 'installation', 'conflicts_of_interest', 'version',
         'license', 'short_description'),
        # 2: Challenge
        ('title', 'abstract', 'background', 'methods', 'content_description',
         'usage_notes', 'conflicts_of_interest', 'version', 'license',
         'short_description'),
        # 3: Model
        ('title', 'abstract', 'background', 'methods', 'content_description',
         'usage_notes', 'installation', 'conflicts_of_interest', 'version',
         'license', 'short_description'),
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
        # 3: Model
        {'content_description': 'Model Description',
         'methods': 'Technical Implementation',
         'installation': 'Installation and Requirements'},
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
        Total storage used in bytes.

        This includes the total size of new files uploaded to this
        project, as well as the total size of files published in past
        versions of this CoreProject.  (The QuotaManager should ensure
        that the same file is not counted twice in this total.)
        """
        current = self.quota_manager().bytes_used
        published = self.core_project.total_published_size
        return current + published

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
        # Folder must be a subfolder of the file root
        # (but not necessarily exist or be a directory)
        inspect_dir = os.path.join(self.file_root(), subdir)
        if inspect_dir.startswith(self.file_root()):
            return inspect_dir
        else:
            raise Exception('Invalid directory request')

    def file_url(self, subdir, file):
        """
        Url of a file to download in this project
        """
        return reverse('serve_active_project_file',
            args=(self.slug, os.path.join(subdir, file)))

    def file_display_url(self, subdir, file):
        """
        URL of a file to display in this project
        """
        return reverse('display_active_project_file',
            args=(self.slug, os.path.join(subdir, file)))

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
        archived_project = ArchivedProject(archive_reason=archive_reason,
            slug=self.slug)

        modified_datetime = self.modified_datetime

        # Direct copy over fields
        for attr in [f.name for f in Metadata._meta.fields] + [f.name for f in SubmissionInfo._meta.fields]:
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
        for parent_project in self.parent_projects.all():
            archived_project.parent_projects.add(parent_project)
        if self.resource_type.id == 1:
            languages = self.programming_languages.all()
            if languages:
                archived_project.programming_languages.add(*list(languages))

        # Voluntary delete
        if archive_reason == 1:
            self.clear_files()
        else:
            # Move over files
            os.rename(self.file_root(), archived_project.file_root())

        # Copy the ActiveProject timestamp to the ArchivedProject.
        # Since this is an auto_now field, save() doesn't allow
        # setting an arbitrary value.
        queryset = ArchivedProject.objects.filter(id=archived_project.id)
        queryset.update(modified_datetime=modified_datetime)

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
        self.integrity_errors = ErrorList()

        # Invitations
        for invitation in self.authorinvitations.filter(is_active=True):
            self.integrity_errors.append(
                'Outstanding author invitation to {0}'.format(invitation.email))

        # Storage requests
        for storage_request in self.storagerequests.filter(
                is_active=True):
            self.integrity_errors.append('Outstanding storage request')

        # Authors
        for author in self.authors.all().order_by('display_order'):
            if not author.get_full_name():
                self.integrity_errors.append('Author {0} has not fill in name'.format(author.user.username))
            if not author.affiliations.all():
                self.integrity_errors.append('Author {0} has not filled in affiliations'.format(author.user.username))

        # Metadata
        for attr in ActiveProject.REQUIRED_FIELDS[self.resource_type.id]:
            value = getattr(self, attr)
            text = unescape(strip_tags(str(value)))
            if value is None or not text or text.isspace():
                l = self.LABELS[self.resource_type.id][attr] if attr in self.LABELS[self.resource_type.id] else attr.title().replace('_', ' ')
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
        Assign an editor to the project and set the submission status to the
        edit stage.
        """
        self.editor = editor
        self.submission_status = 20
        self.editor_assignment_datetime = timezone.now()
        self.save()

    def reassign_editor(self, editor):
        """
        Reassign the current project editor with new editor
        """
        self.editor = editor
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

        with transaction.atomic():
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

    def publish(self, slug=None, make_zip=True, title=None):
        """
        Create a published version of this project and update the
        submission status.

        Parameters
        ----------
        slug : the desired custom slug of the published project.
        make_zip : whether to make a zip of all the files.
        """
        if not self.is_publishable():
            raise Exception('The project is not publishable')

        published_project = PublishedProject(has_wfdb=self.has_wfdb())

        # Direct copy over fields
        for attr in [f.name for f in Metadata._meta.fields] + [f.name for f in SubmissionInfo._meta.fields]:
            setattr(published_project, attr, getattr(self, attr))

        published_project.slug = slug or self.slug

        # Create project file root if this is first version or the first
        # version with a different access policy
        if not os.path.isdir(published_project.project_file_root()):
            os.mkdir(published_project.project_file_root())
        os.rename(self.file_root(), published_project.file_root())

        try:
            with transaction.atomic():
                # If this is a new version, previous fields need to be updated
                # and slug needs to be carried over
                if self.version_order:
                    previous_published_projects = self.core_project.publishedprojects.all()

                    slug = previous_published_projects.first().slug
                    title = previous_published_projects.first().title
                    if slug != published_project.slug:
                        raise ValueError(
                            {"message": "The published project has different slugs."})

                # Set the slug if specified
                published_project.slug = slug or self.slug
                published_project.title = title or self.title
                published_project.doi = self.doi

                # Change internal links (that point to files within
                # the active project) to point to their new locations
                # in the published project
                published_project.update_internal_links(old_project=self)

                published_project.save()

                # If this is a new version, all version fields have to be updated
                if self.version_order > 0:
                    published_project.set_version_order()

                # Same content, different objects.
                for reference in self.references.all().order_by('id'):
                    published_reference = PublishedReference.objects.create(
                        description=reference.description,
                        project=published_project)

                for publication in self.publications.all():
                    published_publication = PublishedPublication.objects.create(
                        citation=publication.citation, url=publication.url,
                        project=published_project)

                published_project.set_topics([t.description for t in self.topics.all()])

                for parent_project in self.parent_projects.all():
                    published_project.parent_projects.add(parent_project)

                if self.resource_type.id == 1:
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

                # Set files read only and make zip file if requested
                move_files_as_readonly(published_project.id, self.file_root(),
                    published_project.file_root(), make_zip,
                    verbose_name='Read Only Files - {}'.format(published_project))

                # Remove the ActiveProject
                self.delete()

                return published_project

        except:
            # Move the files to the active project directory
            os.rename(published_project.file_root(), self.file_root())
            raise


def exists_project_slug(slug):
    """
    Whether the slug has been taken by an existing project of any
    kind.
    """
    return bool(ActiveProject.objects.filter(slug=slug)
            or ArchivedProject.objects.filter(slug=slug)
            or PublishedProject.objects.filter(slug=slug))


class LegacyProject(models.Model):
    """
    Temporary model for migrating legacy databases
    """
    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=100)
    abstract = SafeHTMLField(blank=True, default='')
    full_description = SafeHTMLField()
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
            resource_type=ProjectType.objects.get(id=self.resource_type),
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
            os.mkdir(p.project_file_root())
            os.mkdir(p.file_root())
