import os
import shutil
import datetime
from distutils.version import StrictVersion

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from project.managers.publishedproject import PublishedProjectManager
from project.modelcomponents.access import DataAccessRequest, DataAccessRequestReviewer, DUASignature
from project.modelcomponents.fields import SafeHTMLField
from project.modelcomponents.metadata import Metadata, PublishedTopic
from project.modelcomponents.submission import SubmissionInfo
from project.models import AccessPolicy
from project.utility import StorageInfo, clear_directory, get_tree_size
from project.validators import MAX_PROJECT_SLUG_LENGTH, validate_slug, validate_subdir
from user.models import Training


class PublishedProject(Metadata, SubmissionInfo):
    """
    A published project. Immutable snapshot.
    """
    objects = PublishedProjectManager()

    # File storage sizes in bytes
    main_storage_size = models.BigIntegerField(default=0)
    compressed_storage_size = models.BigIntegerField(default=0)
    incremental_storage_size = models.BigIntegerField(default=0)
    publish_datetime = models.DateTimeField(auto_now_add=True)
    has_other_versions = models.BooleanField(default=False)
    deprecated_files = models.BooleanField(default=False)
    # doi = models.CharField(max_length=50, unique=True, validators=[validate_doi])
    # Temporary workaround
    doi = models.CharField(max_length=50, blank=True, null=True)
    slug = models.SlugField(max_length=MAX_PROJECT_SLUG_LENGTH, db_index=True,
        validators=[validate_slug])
    # Fields for legacy pb databases
    is_legacy = models.BooleanField(default=False)
    full_description = SafeHTMLField(default='')

    # For ordering projects with multiple versions
    version_order = models.PositiveSmallIntegerField(default=0)
    is_latest_version = models.BooleanField(default=True)

    # Featured content
    featured = models.PositiveSmallIntegerField(null=True)
    has_wfdb = models.BooleanField(default=False)
    display_publications = models.BooleanField(default=True)
    # Where all the published project files are kept, depending on access.
    PROTECTED_FILE_ROOT = os.path.join(settings.MEDIA_ROOT, 'published-projects')
    # Workaround for development
    # Note that all files located within the *parent directory* of
    # PUBLIC_FILE_ROOT are treated as public (see
    # physionet-django/lightwave/views.py).
    if settings.STATIC_ROOT is None:
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
        unique_together = (('core_project', 'version'),('featured',),)
        default_permissions = ('change',)
        permissions = [
            ('can_edit_featured_content', 'Can edit featured content'),
            ('can_view_access_logs', 'Can view access logs'),
            ('can_view_project_guidelines', 'Can view project guidelines'),
            ('can_view_stats', 'Can view stats')
        ]
        ordering = ('title', 'version_order')

    def __str__(self):
        return ('{0} v{1}'.format(self.title, self.version))

    def is_published(self):
        return True

    def project_file_root(self):
        """
        Root directory containing the published project's files.

        This is the parent directory of the main and special file
        directories.
        """
        return self.files.get_project_file_root(self.slug, self.version, self.access_policy, PublishedProject)

    def file_root(self):
        """
        Root directory where the main user uploaded files are located
        """
        return self.files.get_file_root(self.slug, self.version, self.access_policy, PublishedProject)

    def storage_used(self):
        """
        Bytes of storage used by main files and compressed file if any
        """
        storage_used = self.files.published_project_storage_used(self)
        zip_file_size = self.files.get_zip_file_size(self)

        return storage_used, zip_file_size

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

    def zip_name(self, full=False, legacy=True):
        """
        Name of the zip file. Either base name or full path name.

        If legacy is true, use the project title to generate the file
        name (e.g. "demo-ecg-signal-toolbox-10.5.24.zip").

        If false, use the project slug (e.g. "demoecg-10.5.24.zip").

        Eventually the old style will be replaced with the new style.
        """
        if legacy:
            name = '{}.zip'.format(self.slugged_label())
        else:
            name = '{}-{}.zip'.format(self.slug, self.version)
        if full:
            name = os.path.join(self.project_file_root(), name)
        return name

    def make_zip(self):
        """
        Make a (new) zip file of the main files.
        """
        return self.files.make_zip(project=self)

    def remove_zip(self):
        fname = self.zip_name(full=True)
        if os.path.isfile(fname):
            os.remove(fname)
            self.compressed_storage_size = 0
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
        return self.files.make_checksum_file(self)

    def remove_files(self):
        """
        Remove files of this project
        """
        self.files.rm_dir(self.file_root(), remove_zip=self.remove_zip)
        self.set_storage_info()

    def deprecate_files(self, delete_files):
        """
        Label the project's files as deprecated. Option of deleting
        files.
        """
        self.deprecated_files = True
        self.save()
        if delete_files:
            self.remove_files()

    def get_inspect_dir(self, subdir):
        """
        Return the folder to inspect if valid. subdir joined onto the
        main file root of this project.
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
        full_file_name = os.path.join(subdir, file)
        return reverse('serve_published_project_file',
            args=(self.slug, self.version, full_file_name))

    def file_display_url(self, subdir, file):
        """
        URL of a file to display in this project
        """
        return reverse('display_published_project_file',
            args=(self.slug, self.version, os.path.join(subdir, file)))

    def can_approve_requests(self, user):
        """
        Whether the user can view and respond to access requests to self managed
        projects
        """
        # check whether user is the corresponding author of the project
        is_corresponding = user == self.corresponding_author().user
        return is_corresponding or self.is_data_access_reviewer(user)

    def is_data_access_reviewer(self, user):
        return DataAccessRequestReviewer.objects.filter(
            reviewer=user, is_revoked=False, project=self).exists()

    def get_storage_info(self, force_calculate=True):
        """
        Return an object containing information about the project's
        storage usage. Main, compressed, total files, and allowance.

        This function always returns the cached information stored in
        the model.  The force_calculate argument has no effect.
        """
        main = self.main_storage_size
        compressed = self.compressed_storage_size
        return StorageInfo(allowance=self.core_project.storage_allowance,
            used=main+compressed, include_remaining=False, main_used=main,
            compressed_used=compressed)

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

    def submitting_user(self):
        "User who is the submitting author"
        return self.authors.get(is_submitting=True).user

    def can_publish_new(self, user):
        """
        Whether the user can publish a new version of this project
        """
        if user == self.submitting_user() and not self.core_project.active_new_version():
            return True

        return False

    def can_manage_data_access_reviewers(self, user):
        return user == self.corresponding_author().user

    def add_topic(self, topic_description):
        """
        Tag this project with a topic
        """

        published_topic = PublishedTopic.objects.filter(
            description=topic_description.lower())
        # Create the published topic object first if it doesn't exist
        if published_topic.count():
            published_topic = published_topic.get()
        else:
            published_topic = PublishedTopic.objects.create(
                description=topic_description.lower())

        published_topic.projects.add(self)
        published_topic.project_count += 1
        published_topic.save()

    def remove_topic(self, topic_description):
        """
        Remove the topic tag from this project
        """
        published_topic = PublishedTopic.objects.filter(
            description=topic_description.lower())

        if published_topic.count():
            published_topic = published_topic.get()
            published_topic.projects.remove(self)
            published_topic.project_count -= 1
            published_topic.save()

            if published_topic.project_count == 0:
                published_topic.delete()

    def set_topics(self, topic_descriptions):
        """
        Set the topic tags for this project.

        topic_descriptions : list of description strings
        """
        existing_descriptions = [t.description for t in self.topics.all()]

        # Add these topics
        for td in set(topic_descriptions) - set(existing_descriptions):
            self.add_topic(td)

        # Remove these topics
        for td in set(existing_descriptions) - set(topic_descriptions):
            self.remove_topic(td)

    def set_version_order(self):
        """
        Order the versions by number.
        Then it set a correct version order and a correct latest version
        """
        published_projects = self.core_project.get_published_versions()
        project_versions = []
        for project in published_projects:
            project_versions.append(project.version)
        sorted_versions = sorted(project_versions, key=StrictVersion)

        for indx, version in enumerate(sorted_versions):
            tmp = published_projects.get(version=version)
            tmp.version_order = indx
            tmp.has_other_versions = True
            tmp.is_latest_version = False
            if sorted_versions[-1] == version:
                tmp.is_latest_version = True
            tmp.save()

    def get_paper_count(self):
        """
        Get a count of the number of files/directories minus one (for the index.html) in a projects papers folder.
        This is designed to work with the project structure for challenges but could be used elsewhere also.
        """
        paper_count = len(os.listdir(os.path.join(self.file_root(), 'papers/'))) - 1
        return(paper_count)

    def get_program_count(self):
        """
        Get a count of the number of files/directories minus one (for the index.html) in a projects sources folder.
        This is designed to work with the project structure for challenges but could be used elsewhere also.
        """
        program_count = len(os.listdir(os.path.join(self.file_root(), 'sources/'))) - 1
        return(program_count)

    def embargo_end_date(self):
        """
        Get the end date for the files under embargo by adding the number of days for embargo to the published date.
        """
        if self.embargo_files_days:
            return self.publish_datetime + datetime.timedelta(days=self.embargo_files_days)
        else:
            return datetime.datetime(1, 1, 1, 0, 0)

    def embargo_active(self):
        """
        Determine if the embargo should still be in effect based on the embargo_end_date and the current .now date
        """
        if self.embargo_files_days and (self.embargo_end_date() > timezone.now()):
            return True
        else:
            return False
