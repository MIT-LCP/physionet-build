import os
import re
import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.html import escape, format_html, mark_safe
from html2text import html2text
from project.fields import SafeHTMLField
from project.modelcomponents.access import AccessPolicy, AnonymousAccess
from project.modelcomponents.authors import Affiliation
from project.utility import LinkFilter, get_directory_info, get_file_info, list_items
from project.validators import validate_title, validate_topic, validate_version


def get_document_path(instance, filename):
    extension = filename.split('.')[-1]
    name = instance.document_type.name.replace(" ", "_")
    return f'ethics/{name}_{uuid.uuid4()}.{extension}'


class Metadata(models.Model):
    """
    Visible content of a published or unpublished project.

    Every project (ActiveProject, PublishedProject) inherits
    from this class as well as SubmissionInfo.
    The difference is that the fields of this class
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
    access_policy = models.SmallIntegerField(choices=AccessPolicy.choices(), default=AccessPolicy.OPEN)

    license = models.ForeignKey('project.License', null=True,
        on_delete=models.SET_NULL)
    dua = models.ForeignKey('project.DUA', null=True, on_delete=models.SET_NULL)
    project_home_page = models.URLField(default='', blank=True)
    parent_projects = models.ManyToManyField('project.PublishedProject',
        blank=True, related_name='derived_%(class)ss')
    programming_languages = models.ManyToManyField(
        'project.ProgrammingLanguage', related_name='%(class)ss', blank=True)

    core_project = models.ForeignKey('project.CoreProject',
                                     related_name='%(class)ss',
                                     on_delete=models.CASCADE)
    allow_file_downloads = models.BooleanField(default=True)
    # Store the number of days a project's files should be under embargo
    embargo_files_days = models.SmallIntegerField(default=None, null=True, blank=True)
    georestricted = models.BooleanField(default=False, null=True)

    ethics_statement = SafeHTMLField(blank=True)
    required_trainings = models.ManyToManyField('user.TrainingType', related_name='%(class)s')

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

    def display_authors(self, max_authors=3):
        """
        Get a truncated display string of author names.
        Shows up to max_authors names, with 'et al.' if there are more.
        """
        authors = list(self.authors.all().order_by('display_order'))
        names = ', '.join(a.get_full_name() for a in authors[:max_authors])
        return f'{names}, et al.' if len(authors) > max_authors else names

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
        citation_styles = settings.PLATFORM_WIDE_CITATION

        return citation_styles

    def abstract_text_content(self):
        """
        Returns abstract as plain text.
        """
        return html2text(self.abstract)

    def update_internal_links(self, old_project):
        """
        Update internal links after the project is moved to a new URL.

        Internal links and subresources ("href" and "src" attributes)
        within the project description field may point to particular
        files in the project.  When an active project becomes
        published, or a published project is cloned as a new active
        project, these links should be updated to point to the new
        project location.

        For example, if self is a PublishedProject with slug='mitbih'
        and version='1.0.0', and old_project is an ActiveProject with
        slug='SHuKI1APLrwWCqxSQnSk', then:

        - <a href="/project/SHuKI1APLrwWCqxSQnSk/files/RECORDS">
          becomes <a href="/files/mitbih/1.0.0/RECORDS">

        - <a href="/project/SHuKI1APLrwWCqxSQnSk/preview/RECORDS">
          becomes <a href="/content/mitbih/1.0.0/RECORDS">

        (and vice versa if self and old_project are swapped.)

        Internal links are also changed to be relative to the server
        root:

        - <a href="RECORDS"> becomes
          <a href="/content/mitbih/1.0.0/RECORDS">

        - <a href="https://physionet.org/files/mitbih/1.0.0/RECORDS"> becomes
          <a href="/files/mitbih/1.0.0/RECORDS">
        """

        old_file_url = old_project.file_base_url()
        old_display_url = old_project.file_display_base_url()
        new_file_url = self.file_base_url()
        new_display_url = self.file_display_base_url()

        lf = LinkFilter(base_url=old_display_url,
                        prefix_map={old_display_url: new_display_url,
                                    old_file_url: new_file_url})

        for field in ('abstract', 'background', 'methods',
                      'content_description', 'usage_notes',
                      'installation', 'acknowledgements',
                      'conflicts_of_interest', 'release_notes'):
            text = getattr(self, field)
            text = lf.convert(text)
            setattr(self, field, text)

    def file_base_url(self):
        """
        Return the base URL for downloading files from this project.
        """
        # file_url requires a non-empty path
        url = self.file_url('', 'x')
        assert url.endswith('/x')
        return url[:-1]

    def file_display_base_url(self):
        """
        Return the base URL for displaying files in this project.
        """
        # file_display_url requires a non-empty path
        url = self.file_display_url('', 'x')
        assert url.endswith('/x')
        return url[:-1]

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
        self.files.fwrite(fname, self.license_content(fmt='text'))

    def make_checksum_file(self):
        """
        Make the checksums file for the main files
        """
        return self.files.make_checksum_file(self)

    def get_directory_content(self, subdir=''):
        """
        Return information for displaying files and directories from
        the project's file root.
        """
        inspect_dir = self.get_inspect_dir(subdir)
        return self.files.get_project_directory_content(inspect_dir, subdir, self.file_display_url, self.file_url)

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

    def generate_anonymous_access(self, hide_authors=False):
        """
        Generate or regenerate anonymous access for the project

        Args:
            hide_authors: If True, author information will be hidden when
                         accessing via the anonymous link (for blind review)
        """
        if not self.anonymous.first():
            anonymous = AnonymousAccess(project=self)
        else:
            anonymous = self.anonymous.first()

        anonymous.hide_authors = hide_authors
        anonymous.save()

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
            prefix = self.future_doi_prefix()
            if prefix:
                doi = prefix + '/*****'
            else:
                doi = None

        rrid_text = f"RRID:{settings.PLATFORM_RRID}." if settings.PLATFORM_RRID else ""
        shared_content = {'year': year,
                          'title': self.title,
                          'version': self.version,
                          'platform_name': settings.SITE_NAME,
                          'rrid': rrid_text}

        if style == 'MLA':

            style_format = ('{author}. "{title}" (version {version}). '
                            '<i>{platform_name}</i> ({year}). {rrid}')

            doi_format = (' <a href="https://doi.org/{doi}">'
                          'https://doi.org/{doi}</a>')

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
                            '{version}). <i>{platform_name}</i>. {rrid}')

            doi_format = (' <a href="https://doi.org/{doi}">'
                          'https://doi.org/{doi}</a>')

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
                            '<i>{platform_name}</i> ({year}). {rrid}')

            doi_format = (' <a href="https://doi.org/{doi}">'
                          'https://doi.org/{doi}</a>')

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
                            "{version}), <i>{platform_name}</i>. {rrid}")

            doi_format = (" Available at: "
                          "<a href='https://doi.org/{doi}'>"
                          "https://doi.org/{doi}</a>")

            if (len(authors) == 1):
                all_authors = authors[0].initialed_name()
            else:
                all_authors = ', '.join(a.initialed_name() for a in
                                        authors[:(len(authors)-1)])
                all_authors += ', and ' + \
                    authors[len(authors)-1].initialed_name()

        elif style == 'Vancouver':

            style_format = ('{author}. {title} (version {version}). '
                            '{platform_name}. {year}. {rrid}')

            doi_format = (' Available from: '
                          '<a href="https://doi.org/{doi}">'
                          'https://doi.org/{doi}</a>')

            all_authors = ', '.join(a.initialed_name(commas=False,
                                    periods=False) for a in authors)

        if doi:
            final_style = style_format + doi_format
            citation_format = format_html(final_style,
                                          author=all_authors,
                                          doi=doi,
                                          **shared_content)

        else:
            final_style = style_format
            citation_format = format_html(final_style,
                                          author=all_authors,
                                          **shared_content)

        return citation_format

    def citation_text_all(self):
        styles = ['MLA', 'APA', 'Chicago', 'Harvard', 'Vancouver']
        citation_dict = {}

        for style in styles:
            citation_dict[style] = self.citation_text(style)

        citation_dict['BibTeX'] = self.citation_text_bibtex()

        return citation_dict

    # Compile regex once at class level for BibTeX escaping
    _BIBTEX_SPECIAL_CHARS = re.compile(r'([\\%#&_${}])')
    _BIBTEX_REPLACEMENTS = {
        '\\': r'\textbackslash{}',
        '%': r'\%', '#': r'\#', '&': r'\&',
        '_': r'\_', '$': r'\$', '{': r'\{', '}': r'\}'
    }

    @classmethod
    def _escape_bibtex(cls, text):
        """Escape special characters for BibTeX compatibility."""
        return cls._BIBTEX_SPECIAL_CHARS.sub(
            lambda m: cls._BIBTEX_REPLACEMENTS[m.group(1)], text
        )

    @classmethod
    def _format_bibtex_author(cls, author):
        """
        Format author name for BibTeX, handling multi-word last names.

        Converts "Van der Berg, John" to "{Van der Berg}, John" so BibTeX
        parsers correctly identify the last name.
        """
        name = author.get_full_name(reverse=True)
        if ', ' in name:
            last_name, first_names = name.split(', ', 1)
            last_name = cls._escape_bibtex(last_name)
            first_names = cls._escape_bibtex(first_names)
            if ' ' in last_name:
                last_name = '{' + last_name + '}'
            return last_name + ', ' + first_names
        return cls._escape_bibtex(name)

    def citation_text_bibtex(self):
        """
        Generate a BibTeX citation for the project.
        """
        authors = self.authors.all().order_by('display_order')

        if self.is_published():
            year = self.publish_datetime.year
            month = self.publish_datetime.strftime('%b').lower()
            doi = self.doi

            if self.is_legacy:
                return ''

            slug = getattr(self, 'slug', 'project')
            version_str = self.version if self.version else ''
            citation_key = f"{settings.SITE_NAME}-{slug}-{version_str}"
        else:
            year = timezone.now().year
            month = timezone.now().strftime('%b').lower()
            prefix = self.future_doi_prefix()
            if prefix:
                doi = prefix + '/*****'
            else:
                doi = None
            citation_key = 'unpublished'

        author_list = ' and '.join(
            self._format_bibtex_author(a) for a in authors
        )

        title = self._escape_bibtex(self.title)

        bibtex_lines = [
            f"@article{{{citation_key},",
            f"  author = {{{author_list}}},",
            f"  title = {{{{{title}}}}},",
            f"  journal = {{{{{settings.SITE_NAME}}}}},",
            f"  year = {{{year}}},",
            f"  month = {month},",
        ]

        if self.version:
            bibtex_lines.append(f"  note = {{Version {self.version}}},")

        if doi:
            bibtex_lines.append(f"  doi = {{{doi}}},")
            bibtex_lines.append(f"  url = {{https://doi.org/{doi}}},")

        bibtex_lines[-1] = bibtex_lines[-1].rstrip(',')
        bibtex_lines.append("}")

        return '\n'.join(bibtex_lines)

    def content_sections(self):
        """
        Return a list of ContentSections that form the project description.

        Each ContentSection contains a fixed header (defined by the
        project type) and an author-editable body.  Some sections are
        optional and the body is allowed to be empty, in which case
        that section should be hidden.
        """
        headers = self.resource_type.content_section_headers()
        return [ContentSection(header, self) for header in headers]


class ContentSection:
    """
    Free-form HTML content that forms part of a project description.

    A project description contains many sections (such as "Abstract",
    "Background", and "Methods"), which follow a particular structure
    that is defined for each project type.

    A ContentSection object encapsulates the author-editable content
    of the section (the "body") together with the fixed metadata (the
    "header").  It has the following attributes:

    - title: the human-readable title of the section

    - html_id: the ID that may be used to link to the section

    - required: True if the section is required (the project should
      not be published if this section is missing)

    - field_name: the name of the corresponding field in Metadata

    - body: the author-editable content of the section

    In the present implementation, every ContentSection corresponds to
    a particular field of the ActiveProject or PublishedProject
    instance (specifically, one of the fields defined in the Metadata
    class.)  In the future, this structure may become dynamic and
    site-configurable.
    """
    def __init__(self, header, project):
        self.header = header
        self.project = project
        self.title = header.title
        self.html_id = header.html_id
        self.required = header.required
        self.field_name = header.field_name

    def __repr__(self):
        return '<{}: {!r}>'.format(type(self).__name__, self.title)

    @property
    def body(self):
        return getattr(self.project, self.field_name)


class Topic(models.Model):
    """
    Topic information to tag ActiveProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    description = models.CharField(max_length=50, validators=[validate_topic])

    class Meta:
        default_permissions = ()
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

    class Meta:
        default_permissions = ()

    def __str__(self):
        return self.description


class BaseReference(models.Model):
    """
    Abstract base class for a bibliographic reference.
    """
    class Meta:
        abstract = True

    order = models.PositiveIntegerField(null=True)
    description = models.CharField(max_length=1000)

    def __str__(self):
        return self.description

    @property
    def html_description(self):
        description = escape(self.description)
        url = self.url
        if url:
            escaped_url = escape(url)
            link = format_html('<a href="{0}">{0}</a>', url)
            description = description.replace(escaped_url, link)
            description = mark_safe(description)
        return description


class Reference(BaseReference):
    """
    Reference field for ActiveProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    URL_PATTERN = re.compile(r'\bhttps?://[^\s<>"\']+', re.IGNORECASE)

    class Meta:
        default_permissions = ()
        unique_together = (('description', 'object_id', 'order'),)

    @property
    def url(self):
        m = self.URL_PATTERN.search(self.description)
        if m:
            return m.group()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.project.content_modified()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.project.content_modified()


class PublishedReference(BaseReference):
    """
    Reference field for PublishedProject
    """
    project = models.ForeignKey('project.PublishedProject',
        related_name='references', on_delete=models.CASCADE)
    url = models.URLField(blank=True, null=True)

    class Meta:
        default_permissions = ()
        unique_together = (('description', 'project', 'order'))


class Contact(models.Model):
    """
    Contact for a PublishedProject
    """
    name = models.CharField(max_length=120)
    affiliations = models.CharField(max_length=(Affiliation.MAX_AFFILIATIONS * (Affiliation.MAX_LENGTH + 2)))
    email = models.EmailField(max_length=255)
    project = models.OneToOneField('project.PublishedProject',
        related_name='contact', on_delete=models.CASCADE)

    class Meta:
        default_permissions = ()


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
    Publication for ActiveProject
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')

    class Meta:
        default_permissions = ()

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

    class Meta:
        default_permissions = ()


class DocumentType(models.Model):
    name = models.CharField(max_length=128)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return self.name


class UploadedDocument(models.Model):
    document_type = models.ForeignKey(DocumentType, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    project = GenericForeignKey('content_type', 'object_id')
    document = models.FileField(upload_to=get_document_path)

    class Meta:
        default_permissions = ()


    def delete(self, *args, **kwargs):
        self.document.delete()
        super().delete(*args, **kwargs)
