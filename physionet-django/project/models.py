from datetime import datetime, timedelta
import hashlib
from html import unescape
import os
import shutil
import uuid
import pdb
import pytz
import stat
import logging
from distutils.version import StrictVersion

import bleach
import ckeditor.fields
from html2text import html2text
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.hashers import check_password, make_password
from django.db import models, DatabaseError, transaction
from django.forms.utils import ErrorList
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, strip_tags
from django.utils.text import slugify
from background_task import background
from django.utils.crypto import get_random_string

from project.quota import DemoQuotaManager
from project.utility import (get_tree_size, get_file_info, get_directory_info,
                             list_items, StorageInfo, list_files,
                             clear_directory)
from project.validators import (validate_doi, validate_subdir,
                                validate_version, validate_slug,
                                MAX_PROJECT_SLUG_LENGTH,
                                validate_title, validate_topic)
from user.validators import validate_affiliation

from physionet.utility import (sorted_tree_files, zip_dir)

LOGGER = logging.getLogger(__name__)

@background()
def move_files_as_readonly(pid, dir_from, dir_to, make_zip):
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


class SafeHTMLField(ckeditor.fields.RichTextField):
    """
    An HTML text field that permits only "safe" content.

    On the client side, this field is displayed as an interactive
    WYSIWYG editor (see ckeditor.fields.RichTextField.)

    On the server side, the HTML text is "cleaned" using the bleach
    library to ensure that all tags are properly closed, entities are
    well-formed, etc., and to remove or escape any unsafe tags or
    attributes.

    The permitted set of tags and attributes is generated from the
    corresponding 'allowedContent' rules in settings.CKEDITOR_CONFIGS
    (which also defines the client-side whitelisting rules and the set
    of options that are visible to the user.)  For example:

        'allowedContent': {
            'a': {'attributes': ['href']},
            'em': True,
            '*': {'attributes': ['title']},
        }

    This would permit the use of 'a' and 'em' tags (all other tags are
    forbidden.)  'a' tags are permitted to have an 'href' attribute,
    and any tag is permitted to have a 'title' attribute.

    NOTE: This class does not use ckeditor's 'disallowedContent'
    rules.  Those rules can be used to perform tag/attribute
    blacklisting on the client side, but will not be enforced on the
    server side.
    """

    # The following protocols may be used in 'href', 'src', and
    # similar attributes.
    _protocols = ['http', 'https', 'ftp', 'mailto']

    # The following attributes are forbidden on the server side even
    # if permitted on client side.  (This is a kludge; permitting
    # 'width' to be set on the client side makes editing tables
    # easier.)
    _attribute_blacklist = {('table', 'width')}

    # The following CSS properties may be set via inline styles (but
    # only on elements for which the 'style' attribute itself is
    # permitted.)
    _styles = ['text-align']

    def __init__(self, config_name='default', strip=False,
                 strip_comments=True, **kwargs):
        super().__init__(config_name=config_name, **kwargs)

        conf = settings.CKEDITOR_CONFIGS[config_name]
        tags = []
        attrs = {}
        for (tag, props) in conf['allowedContent'].items():
            if tag != '*':
                tags.append(tag)
            if isinstance(props, dict) and 'attributes' in props:
                attrs[tag] = []
                for attr in props['attributes']:
                    if (tag, attr) not in self._attribute_blacklist:
                        attrs[tag].append(attr)

        self._cleaner = bleach.Cleaner(tags=tags, attributes=attrs,
                                       styles=self._styles,
                                       protocols=self._protocols,
                                       strip=strip,
                                       strip_comments=strip_comments)

    def clean(self, value, model_instance):
        value = self._cleaner.clean(value)
        return super().clean(value, model_instance)


class Affiliation(models.Model):
    """
    Affiliations belonging to an author
    """
    name = models.CharField(max_length=202, validators=[validate_affiliation])
    author = models.ForeignKey('project.Author', related_name='affiliations',
        on_delete=models.CASCADE)

    class Meta:
        unique_together = (('name', 'author'),)


class PublishedAffiliation(models.Model):
    """
    Affiliations belonging to a published author
    """
    name = models.CharField(max_length=202, validators=[validate_affiliation])
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
    creation_date = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (('user', 'content_type', 'object_id',),
                           ('display_order', 'content_type', 'object_id'))

    def get_full_name(self, reverse=False):
        """
        The name is tied to the profile. There is no form for authors
        to change their names. Return the full name.
        Args:
            reverse: Format of the return string. If False (default) then
                'firstnames lastname'. If True then 'lastname, firstnames'.
        """
        last = self.user.profile.last_name
        first = self.user.profile.first_names
        if reverse:
            return ', '.join([last, first])
        else:
            return ' '.join([first, last])

    def initialed_name(self, commas=True, periods=True):
        """
        Return author's name in citation style.
        """
        last = self.user.profile.last_name
        first = self.user.profile.first_names
        final_string = '{}, {}'.format(
            last, ' '.join('{}.'.format(i[0]) for i in first.split()))

        if not commas:
            final_string = final_string.replace(',', '')
        if not periods:
            final_string = final_string.replace('.', '')

        return final_string

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
            return True
        return False

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
        unique_together = (('user', 'project'),
                           ('display_order', 'project'))

    def get_full_name(self, reverse=False):
        """
        Return the full name.
        Args:
            reverse: Format of the return string. If False (default) then
                'firstnames lastname'. If True then 'lastname, firstnames'.
        """
        if reverse:
            return ', '.join([self.last_name, self.first_names])
        else:
            return ' '.join([self.first_names, self.last_name])

    def set_display_info(self):
        """
        Set the fields used to display the author
        """
        self.name = self.get_full_name()
        self.username = self.user.username
        self.email = self.user.email
        self.text_affiliations = [a.name for a in self.affiliations.all()]

    def initialed_name(self, commas=True, periods=True):

        final_string = '{}, {}'.format(self.last_name, ' '.join('{}.'
                                       .format(i[0]) for i in self.first_names
                                       .split()))

        if not commas:
            final_string = final_string.replace(',', '')
        if not periods:
            final_string = final_string.replace('.', '')

        return final_string


class Topic(models.Model):
    """
    Topic information to tag ActiveProject/ArchivedProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    description = models.CharField(max_length=50, validators=[validate_topic])

    class Meta:
        unique_together = (('description', 'content_type', 'object_id'),)

    def __str__(self):
        return self.description

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.project.content_modified()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.project.content_modified()


class PublishedTopic(models.Model):
    """
    Topic information to tag PublishedProject
    """
    projects = models.ManyToManyField('project.PublishedProject',
        related_name='topics')
    description = models.CharField(max_length=50, validators=[validate_topic])
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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.project.content_modified()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.project.content_modified()


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
    project = models.OneToOneField('project.PublishedProject',
        related_name='contact', on_delete=models.CASCADE)


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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.project.content_modified()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.project.content_modified()


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
    doi = models.CharField(max_length=50, blank=True, null=True)
    # Maximum allowed storage capacity in bytes.
    # Default = 100Mb. Max = 10Tb
    storage_allowance = models.BigIntegerField(default=104857600,
        validators=[MaxValueValidator(109951162777600),
                    MinValueValidator(104857600)])

    def active_new_version(self):
        "Whether there is a new version being worked on"
        return bool(self.activeprojects.filter())

    def get_published_versions(self):
        """
        Return a queryset of PublishedProjects, sorted by version.
        """
        return self.publishedprojects.filter().order_by('version_order')

    @property
    def total_published_size(self):
        """
        Total storage size of the published projects.

        This is the sum of the PublishedProjects'
        incremental_storage_size values (which will be less than the
        sum of the main_storage_size values if there are files that
        are shared between versions) and reflects the actual size of
        the data on disk.
        """
        result = self.publishedprojects \
                     .aggregate(total=models.Sum('incremental_storage_size'))
        # The sum will be None if there are no publishedprojects.  It will
        # also be None if any projects have incremental_storage_size=None.
        return result['total'] or 0


class ProjectType(models.Model):
    """
    The project types available on the platform
    """
    id = models.PositiveSmallIntegerField(primary_key=True)
    name = models.CharField(max_length=20)
    description = models.TextField()


class Metadata(models.Model):
    """
    Visible content of a published or unpublished project.

    Every project (ActiveProject, PublishedProject, and
    ArchivedProject) inherits from this class as well as
    SubmissionInfo.  The difference is that the fields of this class
    contain public information that will be shown on the published
    project pages; SubmissionInfo contains internal information about
    the publication process.

    In particular, the UnpublishedProject modified_datetime will be
    updated when any field of Metadata is altered (see
    UnpublishedProject.save), but not when a field of SubmissionInfo
    is modified.

    New fields should be added to this class only if they affect the
    content of the project as it will be shown when published.
    """

    ACCESS_POLICIES = (
        (0, 'Open'),
        (1, 'Restricted'),
        (2, 'Credentialed'),
    )

    resource_type = models.ForeignKey('project.ProjectType',
                                    db_column='resource_type',
                                    related_name='%(class)ss',
                                    on_delete=models.PROTECT)

    # Main body descriptive metadata
    title = models.CharField(max_length=200, validators=[validate_title])
    abstract = SafeHTMLField(max_length=10000, blank=True)
    background = SafeHTMLField(blank=True)
    methods = SafeHTMLField(blank=True)
    content_description = SafeHTMLField(blank=True)
    usage_notes = SafeHTMLField(blank=True)
    installation = SafeHTMLField(blank=True)
    acknowledgements = SafeHTMLField(blank=True)
    conflicts_of_interest = SafeHTMLField(blank=True)
    version = models.CharField(max_length=15, default='', blank=True,
                               validators=[validate_version])
    release_notes = SafeHTMLField(blank=True)

    # Short description used for search results, social media, etc
    short_description = models.CharField(max_length=250, blank=True)

    # Access information
    access_policy = models.SmallIntegerField(choices=ACCESS_POLICIES,
                                             default=0)
    is_self_managed_access = models.BooleanField(default=False)
    self_managed_dua = SafeHTMLField(blank=True, default='')
    self_managed_request_template = SafeHTMLField(blank=True, default='')

    license = models.ForeignKey('project.License', null=True,
        on_delete=models.SET_NULL)
    project_home_page = models.URLField(default='', blank=True)
    parent_projects = models.ManyToManyField('project.PublishedProject',
        blank=True, related_name='derived_%(class)ss')
    programming_languages = models.ManyToManyField(
        'project.ProgrammingLanguage', related_name='%(class)ss', blank=True)

    core_project = models.ForeignKey('project.CoreProject',
                                     related_name='%(class)ss',
                                     on_delete=models.CASCADE)

    class Meta:
        abstract = True

    def is_published(self):
        if isinstance(self, PublishedProject):
            return True
        else:
            return False

    def author_contact_info(self, only_submitting=False):
        """
        Get the names and emails of the project's authors.
        """
        if only_submitting:
            user = self.authors.get(is_submitting=True).user
            return user.email, user.get_full_name
        else:
            authors = self.authors.all().order_by('display_order')
            users = [a.user for a in authors]
            return ((u.email, u.get_full_name()) for u in users)

    def corresponding_author(self):
        return self.authors.get(is_corresponding=True)

    def submitting_author(self):
        return self.authors.get(is_submitting=True)

    def author_list(self):
        """
        Get the project's authors in the correct display order.
        """
        return self.authors.all().order_by('display_order')

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

    def get_platform_citation(self):
        """
        Returns the information needed to generate the standard platform
        citation in multiple formats (MLA, APA, Chicago, Harvard, and
        Vancouver).

        1. MLA (8th edition) [https://owl.purdue.edu/owl/research_and_citation/
                              mla_style/mla_formatting_and_style_guide/
                              mla_formatting_and_style_guide.html]
        2. APA (7th edition) [https://owl.purdue.edu/owl/research_and_citation/
                              apa_style/apa_style_introduction.html]
        3. Chicago (17th edition) [https://owl.purdue.edu/owl/
                                   research_and_citation/
                                   chicago_manual_17th_edition/
                                   cmos_formatting_and_style_guide/
                                   chicago_manual_of_style_17th_edition.html]
        4. Harvard [https://www.mendeley.com/guides/harvard-citation-guide]
        5. Vancouver [https://guides.lib.monash.edu/ld.php?content_id=14570618]

        Parameters
        ----------
        N/A

        Returns
        -------
        citation_styles [dict]:
            dictionary containing the desired citation style
        """
        citation_styles = {
            'MLA': ('Goldberger, A., et al. "PhysioBank, '
                    'PhysioToolkit, and PhysioNet: Components of a '
                    'new research resource for complex physiologic '
                    'signals. Circulation [Online]. 101 (23), pp. '
                    'e215–e220." (2000).'),
            'APA': ('Goldberger, A., Amaral, L., Glass, L., '
                    'Hausdorff, J., Ivanov, P. C., Mark, R., ... & '
                    'Stanley, H. E. (2000). PhysioBank, '
                    'PhysioToolkit, and PhysioNet: Components of a '
                    'new research resource for complex physiologic '
                    'signals. Circulation [Online]. 101 (23), pp. '
                    'e215–e220.'),
            'Chicago': ('Goldberger, A., L. Amaral, L. Glass, J. '
                        'Hausdorff, P. C. Ivanov, R. Mark, J. E. '
                        'Mietus, G. B. Moody, C. K. Peng, and H. E. '
                        'Stanley. "PhysioBank, PhysioToolkit, and '
                        'PhysioNet: Components of a new research '
                        'resource for complex physiologic signals. '
                        'Circulation [Online]. 101 (23), pp. '
                        'e215–e220." (2000).'),
            'Harvard': ('Goldberger, A., Amaral, L., Glass, L., '
                        'Hausdorff, J., Ivanov, P.C., Mark, R., '
                        'Mietus, J.E., Moody, G.B., Peng, C.K. and '
                        'Stanley, H.E., 2000. PhysioBank, '
                        'PhysioToolkit, and PhysioNet: Components of a '
                        'new research resource for complex physiologic '
                        'signals. Circulation [Online]. 101 (23), pp. '
                        'e215–e220.'),
            'Vancouver': ('Goldberger A, Amaral L, Glass L, Hausdorff J, '
                          'Ivanov PC, Mark R, Mietus JE, Moody GB, Peng '
                          'CK, Stanley HE. PhysioBank, PhysioToolkit, '
                          'and PhysioNet: Components of a new research '
                          'resource for complex physiologic signals. '
                          'Circulation [Online]. 101 (23), pp. '
                          'e215–e220.')
        }

        return citation_styles

    def abstract_text_content(self):
        """
        Returns abstract as plain text.
        """
        return html2text(self.abstract)

    def edit_log_history(self):
        """
        Get a list of EditLog objects in submission order.

        Every object corresponds to a single submission from the
        author (and objects are listed in that order), but also
        includes the details of the editor's response (if any) to that
        particular submission.
        """
        return self.edit_logs.order_by('submission_datetime').all()

    def copyedit_log_history(self):
        """
        Get a list of CopyeditLog objects in creation order.

        Every object represents a point in time when the project was
        "opened for copyediting" (which happens once when the project
        is "accepted", and may happen again if the authors
        subsequently request further changes.)
        """
        return self.copyedit_logs.order_by('start_datetime').all()

    def info_card(self, include_emails=True, force_calculate=False):
        """
        Get all the information needed for the project info card
        seen by an admin
        """
        authors, author_emails = self.get_author_info(include_emails=include_emails)
        storage_info = self.get_storage_info(force_calculate=force_calculate)
        edit_logs = self.edit_log_history()
        for e in edit_logs:
            e.set_quality_assurance_results()
        copyedit_logs = self.copyedit_log_history()
        # The last published version. May be None.
        latest_version = self.core_project.publishedprojects.all().last()
        return authors, author_emails, storage_info, edit_logs, copyedit_logs, latest_version

    def license_content(self, fmt):
        """
        Get the license content of the project's license in text or html
        content. Takes the selected license and fills in the year and
        copyright holder.
        """
        authors = self.authors.all().order_by('display_order')
        author_names = ', '.join(a.get_full_name() for a in authors) + '.'

        if fmt == 'text':
            content = self.license.text_content
            content = content.replace('<COPYRIGHT HOLDER>', author_names, 1)
            content = content.replace('<YEAR>', str(timezone.now().year), 1)
        elif fmt == 'html':
            content = self.license.html_content
            content = content.replace('&lt;COPYRIGHT HOLDER&gt;', author_names, 1)
            content = content.replace('&lt;YEAR&gt;', str(timezone.now().year), 1)

        return content

    def create_license_file(self):
        """
        Create a file containing the text of the project license.

        A file 'LICENSE.txt' is created at the top level of the
        project directory, replacing any existing file with that name.
        """
        fname = os.path.join(self.file_root(), 'LICENSE.txt')
        if os.path.isfile(fname):
            os.remove(fname)
        with open(fname, 'x') as outfile:
            outfile.write(self.license_content(fmt='text'))

    def get_directory_content(self, subdir=''):
        """
        Return information for displaying files and directories from
        the project's file root.
        """
        # Get folder to inspect if valid
        inspect_dir = self.get_inspect_dir(subdir)
        file_names, dir_names = list_items(inspect_dir)
        display_files, display_dirs = [], []

        # Files require desciptive info and download links
        for file in file_names:
            file_info = get_file_info(os.path.join(inspect_dir, file))
            file_info.url = self.file_display_url(subdir=subdir, file=file)
            file_info.raw_url = self.file_url(subdir=subdir, file=file)
            file_info.download_url = file_info.raw_url + '?download'
            display_files.append(file_info)

        # Directories require links
        for dir_name in dir_names:
            dir_info = get_directory_info(os.path.join(inspect_dir, dir_name))
            dir_info.full_subdir = os.path.join(subdir, dir_name)
            display_dirs.append(dir_info)

        return display_files, display_dirs

    def schema_org_resource_type(self):
        """
        Return a valid https://schema.org resource type.
        """
        type_map = {0: 'Dataset',  # database
                    1: 'SoftwareSourceCode',  # software
                    2: 'Dataset',  # challenge
                    3: 'Dataset'  # model
                    }

        try:
            return type_map[self.resource_type]
        except KeyError:
            return 'Dataset'

    def is_valid_passphrase(self, raw_passphrase):
        """
        Checks if passphrase is valid for project
        """
        anonymous = self.anonymous.first()
        if not anonymous:
            return False

        return anonymous.check_passphrase(raw_passphrase)

    def generate_anonymous_access(self):
        """
        Checks if passphrase is valid for project
        """
        if not self.anonymous.first():
            anonymous = AnonymousAccess(project=self)
        else:
            anonymous = self.anonymous.first()

        return anonymous.generate_access()

    def get_anonymous_url(self):
        """
        Returns current url for anonymous access
        """
        anonymous = self.anonymous.first()
        if not anonymous:
            return False

        return anonymous.url

    def citation_text(self, style):
        """
        Citation information in multiple formats (MLA, APA, Chicago,
        Harvard, and Vancouver).

        1. MLA (8th edition) [https://owl.purdue.edu/owl/research_and_citation/
                              mla_style/mla_formatting_and_style_guide/
                              mla_formatting_and_style_guide.html]
        2. APA (7th edition) [https://owl.purdue.edu/owl/research_and_citation/
                              apa_style/apa_style_introduction.html]
        3. Chicago (17th edition) [https://owl.purdue.edu/owl/
                                   research_and_citation/
                                   chicago_manual_17th_edition/
                                   cmos_formatting_and_style_guide/
                                   chicago_manual_of_style_17th_edition.html]
        4. Harvard [https://www.mendeley.com/guides/harvard-citation-guide]
        5. Vancouver [https://guides.lib.monash.edu/ld.php?content_id=14570618]

        Parameters
        ----------
        style [string]:
            ['MLA', 'APA', 'Chicago', 'Harvard', 'Vancouver']

        Returns
        -------
        citation_format [string]:
            string containing the desired citation style
        """
        authors = self.authors.all().order_by('display_order')

        if self.is_published():

            year = self.publish_datetime.year
            doi = self.doi

            if self.is_legacy:
                return ''

        else:
            """
            Since the project is not yet published, the current year is used in
            place of the publication year, and '*****' is used in place of the
            DOI suffix.
            """
            year = timezone.now().year
            doi = '10.13026/*****'

        shared_content = {'year': year,
                          'title': self.title,
                          'version': self.version}

        if style == 'MLA':

            style_format = ('{author}. "{title}" (version {version}). '
                            '<i>PhysioNet</i> ({year})')

            doi_format = (', <a href="https://doi.org/{doi}">'
                          'https://doi.org/{doi}</a>.')

            if (len(authors) == 1):
                all_authors = authors[0].get_full_name(reverse=True)
            elif (len(authors) == 2):
                first_author = authors[0].get_full_name(reverse=True)
                second_author = authors[1].get_full_name()
                all_authors = first_author + ', and ' + second_author
            else:
                all_authors = authors[0].get_full_name(reverse=True)
                all_authors += ', et al'

        elif style == 'APA':

            style_format = ('{author} ({year}). {title} (version '
                            '{version}). <i>PhysioNet</i>')

            doi_format = ('. <a href="https://doi.org/{doi}">'
                          'https://doi.org/{doi}</a>.')

            if (len(authors) == 1):
                all_authors = authors[0].initialed_name()
            elif (len(authors) == 2):
                first_author = authors[0].initialed_name()
                second_author = authors[1].initialed_name()
                all_authors = first_author + ', & ' + second_author
            elif (len(authors) > 20):
                all_authors = ', '.join(
                    a.initialed_name() for a in authors[0:19])
                all_authors += ', ... ' \
                    + authors[len(authors)-1].initialed_name()
            else:
                all_authors = ', '.join(a.initialed_name() for a in
                                        authors[:(len(authors)-1)])
                all_authors += ', & ' + \
                    authors[len(authors)-1].initialed_name()

        elif style == 'Chicago':

            style_format = ('{author}. "{title}" (version {version}). '
                            '<i>PhysioNet</i> ({year})')

            doi_format = ('. <a href="https://doi.org/{doi}">'
                          'https://doi.org/{doi}</a>.')

            if (len(authors) == 1):
                all_authors = authors[0].get_full_name(reverse=True)
            else:
                all_authors = ', '.join(
                    a.get_full_name(reverse=True)
                    for a in authors[:(len(authors)-1)])
                all_authors += ', and ' + \
                    authors[len(authors)-1].get_full_name()

        elif style == 'Harvard':

            style_format = ("{author} ({year}) '{title}' (version "
                            "{version}), <i>PhysioNet</i>")

            doi_format = (". Available at: "
                          "<a href='https://doi.org/{doi}'>"
                          "https://doi.org/{doi}</a>.")

            if (len(authors) == 1):
                all_authors = authors[0].initialed_name()
            else:
                all_authors = ', '.join(a.initialed_name() for a in
                                        authors[:(len(authors)-1)])
                all_authors += ', and ' + \
                    authors[len(authors)-1].initialed_name()

        elif style == 'Vancouver':

            style_format = ('{author}. {title} (version {version}). '
                            'PhysioNet. {year}')

            doi_format = ('. Available from: '
                          '<a href="https://doi.org/{doi}">'
                          'https://doi.org/{doi}</a>.')

            all_authors = ', '.join(a.initialed_name(commas=False,
                                    periods=False) for a in authors)

        if doi:
            final_style = style_format + doi_format
            citation_format = format_html(final_style,
                                          author=all_authors,
                                          doi=doi,
                                          **shared_content)

        else:
            final_style = style_format + '.'
            citation_format = format_html(final_style,
                                          author=all_authors,
                                          **shared_content)

        return citation_format

    def citation_text_all(self):
        styles = ['MLA', 'APA', 'Chicago', 'Harvard', 'Vancouver']
        citation_dict = {}

        for style in styles:
            citation_dict[style] = self.citation_text(style)

        return citation_dict


class SubmissionInfo(models.Model):
    """
    Submission information, inherited by all projects.

    Every project (ActiveProject, PublishedProject, and
    ArchivedProject) inherits from this class as well as Metadata.
    The difference is that the fields of this class contain internal
    information about the publication process; Metadata contains the
    public information that will be shown on the published project
    pages.

    In particular, UnpublishedProject.modified_datetime will be
    updated when any field of Metadata is altered (see
    UnpublishedProject.save), but not when a field of SubmissionInfo
    is modified.

    New fields should be added to this class only if they do not
    affect the content of the project as it will be shown when
    published.
    """

    editor = models.ForeignKey('user.User',
        related_name='editing_%(class)ss', null=True,
        on_delete=models.SET_NULL, blank=True)
    # The very first submission
    submission_datetime = models.DateTimeField(null=True, blank=True)
    author_comments = models.CharField(max_length=10000, default='', blank=True)
    editor_assignment_datetime = models.DateTimeField(null=True, blank=True)
    # The last revision request (if any)
    revision_request_datetime = models.DateTimeField(null=True, blank=True)
    # The last resubmission (if any)
    resubmission_datetime = models.DateTimeField(null=True, blank=True)
    editor_accept_datetime = models.DateTimeField(null=True, blank=True)
    # The last copyedit (if any)
    copyedit_completion_datetime = models.DateTimeField(null=True, blank=True)
    author_approval_datetime = models.DateTimeField(null=True, blank=True)

    # When the submitting project was created
    creation_datetime = models.DateTimeField(auto_now_add=True)

    edit_logs = GenericRelation('project.EditLog')
    copyedit_logs = GenericRelation('project.CopyeditLog')

    # For ordering projects with multiple versions
    version_order = models.PositiveSmallIntegerField(default=0)

    # Anonymous access
    anonymous = GenericRelation('project.AnonymousAccess')

    class Meta:
        abstract = True

    def quota_manager(self):
        """
        Return a QuotaManager for this project.

        This can be used to calculate the project's disk usage
        (represented by the bytes_used and inodes_used properties of
        the QuotaManager object.)
        """
        allowance = self.core_project.storage_allowance
        published = self.core_project.total_published_size
        limit = allowance - published

        # DemoQuotaManager needs to know the project's toplevel
        # directory as well as its creation time (so that files
        # present in multiple versions can be correctly attributed to
        # the version where they first appeared.)
        quota_manager = DemoQuotaManager(
            project_path=self.file_root(),
            creation_time=self.creation_datetime)
        quota_manager.set_limits(bytes_hard=limit, bytes_soft=limit)
        return quota_manager


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


class PublishedProject(Metadata, SubmissionInfo):
    """
    A published project. Immutable snapshot.

    """
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

    is_latest_version = models.BooleanField(default=True)
    # Featured content
    featured = models.PositiveSmallIntegerField(null=True)
    has_wfdb = models.BooleanField(default=False)
    display_publications = models.BooleanField(default=True)
    # Where all the published project files are kept, depending on access.
    PROTECTED_FILE_ROOT = os.path.join(settings.MEDIA_ROOT, 'published-projects')
    # Workaround for development
    if 'development' in os.environ['DJANGO_SETTINGS_MODULE']:
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

    def __str__(self):
        return ('{0} v{1}'.format(self.title, self.version))

    def project_file_root(self):
        """
        Root directory containing the published project's files.

        This is the parent directory of the main and special file
        directories.
        """
        if self.access_policy:
            return os.path.join(PublishedProject.PROTECTED_FILE_ROOT, self.slug)
        else:
            return os.path.join(PublishedProject.PUBLIC_FILE_ROOT, self.slug)

    def file_root(self):
        """
        Root directory where the main user uploaded files are located
        """
        return os.path.join(self.project_file_root(), self.version)

    def storage_used(self):
        """
        Bytes of storage used by main files and compressed file if any
        """
        main = get_tree_size(self.file_root())
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
            name = os.path.join(self.project_file_root(), name)
        return name

    def make_zip(self):
        """
        Make a (new) zip file of the main files.
        """
        fname = self.zip_name(full=True)
        if os.path.isfile(fname):
            os.remove(fname)

        zip_dir(zip_name=fname, target_dir=self.file_root(),
            enclosing_folder=self.slugged_label())

        self.compressed_storage_size = os.path.getsize(fname)
        self.save()

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
        fname = os.path.join(self.file_root(), 'SHA256SUMS.txt')
        if os.path.isfile(fname):
            os.remove(fname)

        with open(fname, 'w') as outfile:
            for f in sorted_tree_files(self.file_root()):
                if f != 'SHA256SUMS.txt':
                    h = hashlib.sha256()
                    with open(os.path.join(self.file_root(), f), 'rb') as fp:
                        block = fp.read(h.block_size)
                        while block:
                            h.update(block)
                            block = fp.read(h.block_size)
                    outfile.write('{} {}\n'.format(h.hexdigest(), f))

        self.set_storage_info()

    def remove_files(self):
        """
        Remove files of this project
        """
        clear_directory(self.file_root())
        self.remove_zip()
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

    def has_access(self, user):
        """
        Whether the user has access to this project's files
        """
        if self.deprecated_files:
            return False

        if self.access_policy == 2 and (
            not user.is_authenticated or not user.is_credentialed):
            return False
        elif self.access_policy == 1 and not user.is_authenticated:
            return False

        if self.is_self_managed_access:
            return DataAccessRequest.objects.filter(
                project=self, requester=user,
                status=DataAccessRequest.ACCEPT_REQUEST_VALUE).exists()
        elif self.access_policy:
            return DUASignature.objects.filter(
                project=self, user=user).exists()

        return True

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
    html_content = SafeHTMLField(default='')
    home_page = models.URLField()
    # A project must choose a license with a matching access policy and
    # compatible resource type
    access_policy = models.PositiveSmallIntegerField(choices=Metadata.ACCESS_POLICIES,
        default=0)
    # A license can be used for one or more resource types.
    # This is a comma delimited char field containing allowed types.
    # ie. '0' or '0,2' or '1,3,4'
    resource_types = models.CharField(max_length=100)
    # A protected license has associated DUA content
    dua_name = models.CharField(max_length=100, blank=True, default='')
    dua_html_content = SafeHTMLField(blank=True, default='')

    def __str__(self):
        return self.name

    def dua_text_content(self):
        """
        Returns dua_html_content as plain text. Used when adding the DUA to
        plain text emails.
        """
        return html2text(self.dua_html_content)


class DUASignature(models.Model):
    """
    Log of user signing DUA
    """
    project = models.ForeignKey('project.PublishedProject',
        on_delete=models.CASCADE)
    user = models.ForeignKey('user.User', on_delete=models.CASCADE,
                             related_name='dua_signatures')
    sign_datetime = models.DateTimeField(auto_now_add=True)


class DataAccessRequest(models.Model):
    PENDING_VALUE = 0
    REJECT_REQUEST_VALUE = 1
    WITHDRAWN_VALUE = 2
    ACCEPT_REQUEST_VALUE = 3

    REJECT_ACCEPT = (
        (REJECT_REQUEST_VALUE, 'Reject'),
        (ACCEPT_REQUEST_VALUE, 'Accept'),
    )

    status_texts = {
        PENDING_VALUE: "pending",
        REJECT_REQUEST_VALUE: "rejected",
        WITHDRAWN_VALUE: "withdrawn",
        ACCEPT_REQUEST_VALUE: "accepted"
    }

    DATA_ACCESS_REQUESTS_DAY_LIMIT = 14

    request_datetime = models.DateTimeField(auto_now_add=True)

    requester = models.ForeignKey('user.User', on_delete=models.CASCADE)

    project = models.ForeignKey('project.PublishedProject',
                                related_name='data_access_requests',
                                on_delete=models.CASCADE)

    data_use_title = models.CharField(max_length=200, default='')
    data_use_purpose = SafeHTMLField(blank=False, max_length=10000)

    status = models.PositiveSmallIntegerField(default=0, choices=REJECT_ACCEPT)

    decision_datetime = models.DateTimeField(null=True)

    responder = models.ForeignKey('user.User', null=True,
                                  related_name='data_access_request_user',
                                  on_delete=models.SET_NULL)

    responder_comments = SafeHTMLField(blank=True, max_length=10000)

    def is_accepted(self):
        return self.status == self.ACCEPT_REQUEST_VALUE

    def is_rejected(self):
        return self.status == self.REJECT_REQUEST_VALUE

    def is_withdrawn(self):
        return self.status == self.WITHDRAWN_VALUE

    def is_pending(self):
        return self.status == self.PENDING_VALUE

    def status_text(self):
        return self.status_texts.get(self.status, 'unknown')


class DataAccessRequestReviewer(models.Model):
    """
    A user who is invited to review data access requests of self managed
    credentialing projects.
    """

    class Meta:
        constraints = [models.UniqueConstraint(fields=['project', 'reviewer'],
                                              name='unique project reviewer')]

    project = models.ForeignKey('project.PublishedProject',
                                related_name='data_access_request_reviewers',
                                on_delete=models.CASCADE)

    reviewer = models.ForeignKey('user.User', on_delete=models.CASCADE,
                                 related_name='data_access_request_reviewers')

    added_date = models.DateTimeField(auto_now_add=True)

    is_revoked = models.BooleanField(default=False)

    revocation_date = models.DateTimeField(null=True)

    def revoke(self):
        self.revocation_date = timezone.now()
        self.is_revoked = True
        self.save()


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
    response_message = models.CharField(max_length=10000, default='', blank=True)

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
        ('soundly_produced', 'well_described', 'open_format', 'no_phi',
            'reusable', 'pn_suitable'),
        # 2: Challenge
        ('soundly_produced', 'well_described', 'open_format',
         'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable'),
        # 3: Model
        ('soundly_produced', 'well_described', 'open_format',
         'data_machine_readable', 'reusable', 'no_phi', 'pn_suitable'),
    )
    # The editor's free input fields
    EDITOR_FIELDS = ('editor_comments', 'decision', 'auto_doi')

    COMMON_LABELS = {
        'reusable': 'Does the project include everything needed for reuse by the community?',
        'pn_suitable': 'Is the content suitable for PhysioNet?',
        'editor_comments': 'Comments to authors',
        'no_phi': 'Is the project free of protected health information?',
        'data_machine_readable': 'Are all files machine-readable?'
    }

    LABELS = (
        # 0: Database
        {'soundly_produced': 'Has the data been produced in a sound manner?',
         'well_described': 'Is the data adequately described?',
         'open_format': 'Is the data provided in an open format?',
         'data_machine_readable': 'Are the data files machine-readable?'},
        # 1: Software
        {'soundly_produced': 'Does the software follow best practice in development?',
         'well_described': 'Is the software adequately described?',
         'open_format': 'Is the software provided in an open format?'},
        # 2: Challenge
        {'soundly_produced': 'Has the challenge been produced in a sound manner?',
         'well_described': 'Is the challenge adequately described?',
         'open_format': 'Is all content provided in an open format?'},
        # 3: Model
        {'soundly_produced': 'Does the software follow best practice in development?',
         'well_described': 'Is the software adequately described?',
         'open_format': 'Is the software provided in an open format?'},
    )

    HINTS = {
        'no_phi': [
            'No dates in WFDB header files (or anonymized dates only)?',
            'No identifying information of any individual'
            ' (caregivers as well as patients)?',
            'No ages of individuals above 89 years?',
            'No hidden metadata (e.g. EDF headers)?',
            'No internal timestamps, date-based UUIDs or other identifiers?',
        ],
        'open_format': [
            'No compiled binaries or bytecode?',
            'No minified or obfuscated source code?',
        ],
    }

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    # When the submitting author submits/resubmits
    submission_datetime = models.DateTimeField(auto_now_add=True)
    is_resubmission = models.BooleanField(default=False)
    author_comments = models.CharField(max_length=10000, default='')
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
    editor_comments = models.CharField(max_length=10000)
    auto_doi = models.BooleanField(default=True)

    def set_quality_assurance_results(self):
        """
        Prepare the string fields for the editor's decisions of the
        quality assurance fields, to be displayed. Does nothing if the
        decision has not been made.
        """
        if not self.decision_datetime:
            return

        resource_type = self.project.resource_type

        # See also YES_NO_UNDETERMINED in console/forms.py
        RESPONSE_LABEL = {True: 'Yes', False: 'No', None: 'Undetermined'}

        # Retrieve their labels and results for our resource type
        quality_assurance_fields = self.__class__.QUALITY_ASSURANCE_FIELDS[resource_type.id]

        # Create the labels dictionary for this resource type
        labels = {**self.__class__.COMMON_LABELS, **self.__class__.LABELS[resource_type.id]}

        self.quality_assurance_results = []
        for f in quality_assurance_fields:
            qa_str = '{} {}'.format(labels[f], RESPONSE_LABEL[getattr(self, f)])
            self.quality_assurance_results.append(qa_str)


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
    changelog_summary = models.CharField(default='', max_length=10000, blank=True)
    complete_datetime = models.DateTimeField(null=True)


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


class GCP(models.Model):
    """
    Store all of the Google Cloud information with a relation to a project.
    """
    project = models.OneToOneField('project.PublishedProject', related_name='gcp',
        on_delete=models.CASCADE)
    bucket_name = models.CharField(max_length=150, null=True)
    access_group = models.CharField(max_length=170, null=True)
    is_private = models.BooleanField(default=False)
    sent_zip = models.BooleanField(default=False)
    sent_files = models.BooleanField(default=False)
    managed_by = models.ForeignKey('user.User', related_name='gcp_manager',
        on_delete=models.CASCADE)
    creation_datetime = models.DateTimeField(auto_now_add=True)
    finished_datetime = models.DateTimeField(null=True)


class DataAccess(models.Model):
    """
    Store all the information for different types of file access.
    platform = local, AWS or GCP
    location = the platform specific identifier referencing the data
    """
    PLATFORM_ACCESS = (
        (0, 'local'),
        (1, 'aws-open-data'),
        (2, 'aws-s3'),
        (3, 'gcp-bucket'),
        (4, 'gcp-bigquery'),
    )

    project = models.ForeignKey('project.PublishedProject',
        related_name='%(class)ss', db_index=True, on_delete=models.CASCADE)
    platform = models.PositiveSmallIntegerField(choices=PLATFORM_ACCESS)
    location = models.CharField(max_length=100, null=True)


class AnonymousAccess(models.Model):
    """
    Makes it possible to grant anonymous access (without user auth)
    to a project and its files by authenticating with a passphrase.
    """
    # Project GenericFK
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    # Stores hashed passphrase
    passphrase = models.CharField(max_length=128)

    # Random url
    url = models.CharField(max_length=64)

    # Record tracking
    creation_datetime = models.DateTimeField(auto_now_add=True)
    expiration_datetime = models.DateTimeField(null=True)
    creator = models.ForeignKey('user.User', related_name='anonymous_access_creator',
        on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = (("content_type", "object_id"),)

    def generate_access(self):
        url = self.generate_url()
        passphrase = self.set_passphrase()

        return url, passphrase

    def generate_url(self):
        url = get_random_string(64)

        # Has to be unique
        while AnonymousAccess.objects.filter(url=url).first():
            url = get_random_string(64)

        # Persist new url
        self.url = url
        self.save()

        return url

    def set_passphrase(self):
        # Generate and encode random password
        raw = get_random_string(20)

        # Store encoded passphrase
        self.passphrase = make_password(raw, salt='project.AnonymousAccess')
        self.save()

        return raw

    def check_passphrase(self, raw_passphrase):
        """
        Return a boolean of whether the raw_password was correct. Handles
        hashing formats behind the scenes.
        """
        expire_datetime = self.creation_datetime + timedelta(days=60)
        isnot_expired = timezone.now() < expire_datetime

        return isnot_expired and check_password(raw_passphrase, self.passphrase)


class Metrics(models.Model):
    '''
    Stores the daily and running total view counts for each project, as well
    as date recorded.
    '''
    core_project = models.ForeignKey('project.CoreProject', 
                                     on_delete=models.DO_NOTHING, 
                                     default=None)
    viewcount = models.PositiveIntegerField(default=0)
    running_viewcount = models.PositiveIntegerField(default=0)
    date = models.DateField(default=None)
