import os

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.html import format_html
from html2text import html2text

from project.modelcomponents.access import ACCESS_POLICIES, AnonymousAccess
from project.modelcomponents.fields import SafeHTMLField
from project.utility import LinkFilter, get_file_info, get_directory_info, list_items
from project.validators import validate_version, validate_title, validate_topic


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

    # TODO: Add abstractmethod is_published

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
    
class MetricsLogData(models.Model):
    '''
    Stores the filenames, creation timestamps, and hashes of each log file that is parsed.
    '''
    filename = models.CharField(max_length=128)
    creation_datetime = models.DateTimeField()
    log_hash = models.CharField(max_length=128)
