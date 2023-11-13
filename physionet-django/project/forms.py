import os
import uuid
from collections import OrderedDict

from dal import autocomplete
from django import forms
from django.conf import settings
from django.contrib.contenttypes.forms import BaseGenericInlineFormSet
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db.models.functions import Lower
from django.forms.utils import ErrorList
from django.forms.widgets import HiddenInput
from django.template.defaultfilters import slugify
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.html import format_html
from physionet.settings.base import StorageTypes
from project import utility, validators
from project.models import (
    AccessPolicy,
    ActiveProject,
    Affiliation,
    AnonymousAccess,
    Author,
    AuthorInvitation,
    CoreProject,
    DataAccessRequest,
    DataAccessRequestReviewer,
    DUA,
    License,
    Metadata,
    ProgrammingLanguage,
    Publication,
    PublishedProject,
    Reference,
    StorageRequest,
    Topic,
    exists_project_slug,
    UploadedDocument,
)
from user.models import User, TrainingType
from user.validators import validate_affiliation

INVITATION_CHOICES = (
    (1, 'Accept'),
    (0, 'Decline')
)


class CorrespondingAuthorForm(forms.Form):
    """
    Select a corresponding author for a project
    """
    author = forms.ModelChoiceField(queryset=None)

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        project_authors = project.authors.all().order_by('display_order')
        self.fields['author'].queryset = project_authors
        self.fields['author'].initial = project_authors.get(is_corresponding=True)
        self.fields['author'].empty_label = None

    def update_corresponder(self):
        old_c = self.project.corresponding_author()
        new_c = self.cleaned_data['author']

        if old_c != new_c:
            old_c.is_corresponding, new_c.is_corresponding = False, True
            old_c.save()
            new_c.save()


class TransferAuthorForm(forms.Form):
    """
    Transfer submitting author.
    """
    transfer_author = forms.ModelChoiceField(queryset=None, required=True,
                                             widget=forms.Select(attrs={'onchange': 'set_transfer_author()',
                                                                        'id': 'transfer_author_id'}),
                                             empty_label="Select an author")

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        # Exclude the current submitting author from the queryset
        authors = project.authors.exclude(is_submitting=True).order_by('display_order')
        self.fields['transfer_author'].queryset = authors

    def transfer(self):
        new_author = self.cleaned_data['transfer_author']

        # Assign the new submitting author
        self.project.authors.update(is_submitting=False)
        new_author.is_submitting = True
        new_author.save()


class ActiveProjectFilesForm(forms.Form):
    """
    Inherited form for manipulating project files/directories. Upload
    and create folders, move, rename, delete items.
    """
    # The working subdirectory relative to the project root
    subdir = forms.CharField(widget=forms.HiddenInput(), required=False,
                             validators=[validators.validate_subdir])

    def __init__(self, project, *args, **kwargs):
        super(ActiveProjectFilesForm, self).__init__(*args, **kwargs)
        self.project = project

    def clean_subdir(self):
        """
        Check that the subdirectory exists
        """
        data = self.cleaned_data['subdir']
        file_dir = os.path.join(self.project.file_root(), data)

        if settings.STORAGE_TYPE == StorageTypes.LOCAL and not os.path.isdir(file_dir):
            raise forms.ValidationError('Invalid directory')
        self.file_dir = file_dir

        return data


class MultipleFileInput(forms.ClearableFileInput):
    """
    Variant of ClearableFileInput that allows uploading multiple
    files in a single form field.
    """
    allow_multiple_selected = True

    def __init__(self, attrs={}):
        super().__init__(attrs={'multiple': True, **attrs})


class MultipleFileField(forms.FileField):
    """
    Variant of FileField that allows uploading multiple files in a
    single form field.
    """
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result


class UploadFilesForm(ActiveProjectFilesForm):
    """
    Form for uploading multiple files to a project.
    `subdir` is the project subdirectory relative to the file root.
    """
    file_field = MultipleFileField(widget=MultipleFileInput(
        attrs={'onchange': "check_upload_size_limit('upload');"}), required=False,
        allow_empty_file=True)

    def clean_file_field(self):
        """
        Check for file name, size limits and whether they are readable
        """
        files = self.files.getlist('file_field')

        for file in files:
            validators.validate_filename(file.name)

            # Special error
            if not file:
                raise forms.ValidationError('Could not read file: %(file_name)s',
                    params={'file_name': file.name})

        for file in files:
            if file.size > ActiveProject.INDIVIDUAL_FILE_SIZE_LIMIT:
                raise forms.ValidationError(
                    'File %(file_name)s is larger than the individual size limit: %(individual_size_limit)s',
                    code='exceed_individual_limit',
                    params={'file_name': file.name,
                            'individual_size_limit': utility.readable_size(ActiveProject.INDIVIDUAL_FILE_SIZE_LIMIT)}
                )

        if sum(f.size for f in files) > self.project.core_project.storage_allowance - self.project.storage_used():
            raise forms.ValidationError(
                'Total upload volume exceeds remaining quota',
                code='exceed_remaining_quota',
            )
        return files

    def perform_action(self):
        """
        Upload the files
        """
        errors = ErrorList()
        for file in self.files.getlist('file_field'):
            try:
                self.project.files.fput(self.file_dir, file)
            except FileExistsError:
                errors.append(format_html(
                    'Item named <i>{}</i> already exists', file.name))
            except OSError:
                errors.append(format_html(
                    'Unable to upload <i>{}</i>', file.name))
        return 'Your files have been uploaded', errors


class CreateFolderForm(ActiveProjectFilesForm):
    """
    Form for creating a new folder in a directory
    """
    folder_name = forms.CharField(max_length=validators.MAX_FILENAME_LENGTH,
        required=False, validators=[validators.validate_filename])

    def perform_action(self):
        """
        Create the folder
        """
        errors = ErrorList()
        name = self.cleaned_data['folder_name']

        file_path = os.path.join(self.file_dir, name)
        try:
            self.project.files.mkdir(file_path)
        except FileExistsError:
            errors.append(format_html(
                'Item named <i>{}</i> already exists', name))
        except OSError:
            errors.append(format_html(
                'Unable to create <i>{}</i>', name))
        return 'Your folder has been created', errors


class EditItemsForm(ActiveProjectFilesForm):
    """
    Abstract form for manipulating existing files/directories.
    """
    items = forms.Field(required=False)

    def clean_items(self):
        items = self.data.getlist('items')
        for item in items:
            validators.validate_oldfilename(item)
        return items


class DeleteItemsForm(EditItemsForm):
    """
    Form for deleting existing files/directories.
    """

    def perform_action(self):
        """
        Delete the items
        """
        errors = ErrorList()
        for item in self.cleaned_data['items']:
            path = os.path.join(self.file_dir, item)
            try:
                self.project.files.rm(path)
            except OSError as e:
                if not os.path.exists(path):
                    errors.append(format_html(
                        'Item named <i>{}</i> did not exist', item))
                else:
                    errors.append(format_html(
                        'Unable to delete <i>{}</i>',
                        os.path.relpath(e.filename or path, self.file_dir)))
        return 'Your items have been deleted', errors


class RenameItemForm(EditItemsForm):
    """
    Form for renaming an item in a directory
    """
    new_name = forms.CharField(max_length=validators.MAX_FILENAME_LENGTH,
        required=False, validators=[validators.validate_filename])

    def clean_items(self):
        items = super(RenameItemForm, self).clean_items()
        if len(items) != 1:
            raise forms.ValidationError('Must specify one item to rename')
        return items

    def perform_action(self):
        """
        Rename the items
        """
        errors = ErrorList()
        old_name = self.cleaned_data['items'][0]
        new_name = self.cleaned_data['new_name']

        old_path = os.path.join(self.file_dir, old_name)
        new_path = os.path.join(self.file_dir, new_name)
        try:
            self.project.files.rename(old_path, new_path)
        except FileExistsError:
            errors.append(format_html(
                'Item named <i>{}</i> already exists', new_name))
        except FileNotFoundError:
            errors.append(format_html(
                'Item named <i>{}</i> does not exist', old_name))
        except OSError:
            errors.append(format_html(
                'Unable to rename <i>{}</i> to <i>{}</i>',
                old_name, new_name))
        return 'Your item has been renamed', errors


class MoveItemsForm(EditItemsForm):
    """
    Form for moving items into a target folder
    """
    destination_folder = forms.Field(required=False, widget=forms.Select)

    def __init__(self, project, subdir=None, display_dirs=None,
                 *args, **kwargs):
        """
        Set the choices for the destination folder
        """
        super(MoveItemsForm, self).__init__(project, *args, **kwargs)
        # The choices are only set here for get requests
        if subdir is not None:
            choices = [(d.name, d.name) for d in display_dirs]
            if subdir:
                choices.insert(0, ('../', '(Parent directory)'))
            self.fields['destination_folder'].widget.choices = choices

    def clean(self):
        """
        Selected destination folder:
        - May only be '..' if subdir is not the top level
        - Must not be one of the items selected to be moved
        """
        cleaned_data = super(MoveItemsForm, self).clean()

        destination_folder = cleaned_data['destination_folder']
        selected_items = cleaned_data['items']
        subdir = cleaned_data['subdir']

        if subdir:
            validators.validate_filename_or_parent(destination_folder)
        else:
            validators.validate_filename(destination_folder)

        if destination_folder in selected_items:
            raise forms.ValidationError(format_html(
                'Cannot move folder <i>{}</i> into itself',
                destination_folder))

        self.dest_dir = os.path.normpath(os.path.join(self.file_dir, destination_folder))
        if settings.STORAGE_TYPE == StorageTypes.LOCAL and not os.path.isdir(self.dest_dir):
            raise forms.ValidationError(
                format_html(
                    'Destination folder <i>{}</i> does not exist',
                    destination_folder,
                )
            )

        return cleaned_data

    def perform_action(self):
        """
        Move the items into the selected directory
        """
        errors = ErrorList()
        dest = self.cleaned_data['destination_folder']
        for item in self.cleaned_data['items']:
            path = os.path.join(self.file_dir, item)
            try:
                self.project.files.mv(path, self.dest_dir)
            except FileExistsError:
                errors.append(format_html(
                    'Item named <i>{}</i> already exists in <i>{}</i>',
                    item, dest))
            except OSError:
                if not os.path.exists(path):
                    errors.append(format_html(
                        'Item named <i>{}</i> does not exist', item))
                else:
                    errors.append(format_html(
                        'Unable to move <i>{}</i> into <i>{}</i>', item, dest))
        return 'Your items have been moved', errors


class CreateProjectForm(forms.ModelForm):
    """
    For creating projects
    """
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['resource_type'].label_from_instance = lambda obj: obj.name
    class Meta:
        model = ActiveProject
        fields = ('resource_type', 'title', 'abstract')

    def save(self):
        project = super().save(commit=False)
        # Set the core project and slug
        core_project = CoreProject.objects.create()
        project.core_project = core_project
        slug = get_random_string(20)
        while exists_project_slug(slug):
            slug = get_random_string(20)
        project.slug = slug
        project.save()
        # Create the author object for the user
        author = Author.objects.create(project=project, user=self.user,
            display_order=1, corresponding_email=self.user.get_primary_email(),
            is_submitting=True, is_corresponding=True)
        author.import_profile_info()
        # Create file directory
        project.files.mkdir(project.file_root())
        return project


class NewProjectVersionForm(forms.ModelForm):
    """
    For creating new project versions
    """
    # Enforce non-blank version
    version = forms.CharField(max_length=15)

    def __init__(self, user, latest_project, previous_projects, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.latest_project = latest_project
        self.previous_projects = previous_projects

    class Meta:
        model = ActiveProject
        fields = ('version',)

    def clean_version(self):
        data = self.cleaned_data['version']
        if data in [p.version for p in self.previous_projects]:
            raise forms.ValidationError('Please specify a new unused version.')

        return data

    def save(self):
        project = super().save(commit=False)

        slug = get_random_string(20)
        while exists_project_slug(slug):
            slug = get_random_string(20)
        project.slug = slug

        # Direct copy over fields
        for field in (field.name for field in Metadata._meta.fields):
            if field not in ['slug', 'version', 'creation_datetime', 'embargo_files_days']:
                setattr(project, field, getattr(self.latest_project, field))

        # Set new fields
        project.creation_datetime = timezone.now()
        project.is_new_version = True

        # Change internal links (that point to files within the
        # published project) to point to their new locations in the
        # active project
        project.update_internal_links(old_project=self.latest_project)

        project.save()

        # Copy over the author/affiliation objects
        for p_author in self.latest_project.authors.all():
            if p_author.is_corresponding:
                old_address = p_author.corresponding_email
            else:
                old_address = None
            emails = p_author.user.associated_emails.filter(is_verified=True)
            corresponding_email = (
                emails.filter(email__iexact=old_address).first()
                or emails.filter(is_public=True).first()
                or p_author.user.get_primary_email()
            )
            author = Author.objects.create(
                project=project,
                user=p_author.user,
                display_order=p_author.display_order,
                is_submitting=p_author.is_submitting,
                is_corresponding=p_author.is_corresponding,
                corresponding_email=corresponding_email)

            for p_affiliation in p_author.affiliations.all():
                Affiliation.objects.create(name=p_affiliation.name,
                    author=author)

        # Other related objects
        for p_reference in self.latest_project.references.all():
            reference = Reference.objects.create(
                description=p_reference.description,
                project=project)

        for p_publication in self.latest_project.publications.all():
            publication = Publication.objects.create(
                citation=p_publication.citation, url=p_publication.url,
                project=project)

        for parent_project in self.latest_project.parent_projects.all():
            project.parent_projects.add(parent_project)

        for p_topic in self.latest_project.topics.all():
            Topic.objects.create(project=project, description=p_topic.description)

        documents = []
        content_type = ContentType.objects.get_for_model(ActiveProject)
        for uploaded_document in self.latest_project.uploaded_documents.all():
            uploaded_document.id = None
            uploaded_document.object_id = project.pk
            uploaded_document.content_type = content_type
            uploaded_document.document = ContentFile(
                content=uploaded_document.document.read(), name=uploaded_document.document.name
            )
            documents.append(uploaded_document)

        UploadedDocument.objects.bulk_create(documents)

        project.required_trainings.set(self.latest_project.required_trainings.all())

        current_file_root = project.file_root()
        older_file_root = self.latest_project.file_root()

        ignored_files = ('SHA256SUMS.txt', 'LICENSE.txt')

        if settings.COPY_FILES_TO_NEW_VERSION:
            # NOTE: This assumes the new active project is using the
            # same storage backend as the existing published project.
            project.files.cp_dir(older_file_root, current_file_root, ignored_files=ignored_files)

        return project


class ContentForm(forms.ModelForm):
    """
    Form for editing the content of a project.
    Fields, labels, and help texts may be defined differently for
    different resource types.

    """

    FIELDS = (
        # 0: Database
        ('title', 'abstract', 'background', 'methods', 'content_description',
         'usage_notes', 'release_notes', 'acknowledgements',
         'conflicts_of_interest',
         ),
        # 1: Software
        ('title', 'abstract', 'background', 'content_description',
         'methods', 'installation', 'usage_notes', 'release_notes',
         'acknowledgements', 'conflicts_of_interest', ),
        # 2: Challenge
        ('title', 'abstract', 'background', 'methods', 'content_description',
         'usage_notes', 'release_notes', 'acknowledgements',
         'conflicts_of_interest',
         ),
        # 3: Model
        ('title', 'abstract', 'background', 'methods', 'content_description',
         'installation', 'usage_notes', 'release_notes',
         'acknowledgements', 'conflicts_of_interest',
         ),
    )

    HELP_TEXTS = (
        # 0: Database
        {'methods': '* The methodology employed for the study or research. Describe how the data was collected.',
         'content_description': '* Describe the data, and how the files are named and structured.',
         'usage_notes': '* How the data is to be used. List external documentation pages. List related software developed for the dataset, and any special software required to use the data.'},
        # 1: Software
        {'content_description': '* Describe the software in this project.',
         'methods': 'Details on the technical implementation. ie. the development process, and the underlying algorithms.',
         'usage_notes': '* How the software is to be used. List some example function calls or specify the demo file(s).'},
        # 2: Challenge
        {'background': '* An introduction to the challenge and a description of the objective/s.',
         'methods': '* A timeline for the challenge and rules for participation.',
         'content_description': '* A description of the challenge data and access details.',
         'usage_notes': '* Scoring details, information on submitting an entry, and a link to a sample submission.'},
        # 3: Model
        {'background': '* Introduce the model, providing context.',
         'content_description': '* Describe the model and any supporting data and software.',
         'installation': '* Instructions on how to set up a software environment for using the model.',
         'usage_notes': '* Describe how you intend others to (re)use the model.',
         'methods': 'Details on the technical implementation. ie. the development process, and the underlying algorithms.',
         'usage_notes': '* How the software is to be used. List some example function calls or specify the demo file(s).'},
    )

    class Meta:
        model = ActiveProject
        # This includes fields for all resource types.
        fields = ('title', 'abstract', 'background', 'methods',
                  'content_description', 'installation', 'usage_notes',
                  'acknowledgements', 'conflicts_of_interest',
                  'release_notes',)

        help_texts = {
            'title': '* The title of the resource.',
            'abstract': '* A brief description of the resource and the context in which it was created.',
            'background': '* The content or research background.',
            'installation': '* Instructions on how to install the software, along with the required dependencies. Or specify the files in which they are listed.',
            'acknowledgements': 'Thank the people who helped with the research but did not qualify for authorship. In addition, provide any funding information.',
            'conflicts_of_interest': '* List whether any authors have a financial, commercial, legal, or professional relationship with other organizations, or with the people working with them, that could influence this research. State explicitly if there are none.',
            'release_notes': 'Important notes about the current release, and changes from previous versions.'
        }

    def __init__(self, resource_type, editable=True, **kwargs):
        super(ContentForm, self).__init__(**kwargs)
        self.fields = OrderedDict((k, self.fields[k]) for k in self.FIELDS[resource_type])

        for l in ActiveProject.LABELS[resource_type]:
            self.fields[l].label = ActiveProject.LABELS[resource_type][l]

        for h in self.__class__.HELP_TEXTS[resource_type]:
            self.fields[h].help_text = self.__class__.HELP_TEXTS[resource_type][h]

        if not editable:
            for f in self.fields.values():
                f.disabled = True

        # We require new versions of a previously published project to
        # share the same title
        if self.instance and self.instance.is_new_version:
            self.fields['title'].disabled = True

    def clean_version(self):
        data = self.cleaned_data['version']
        if data in [p.version for p in self.instance.core_project.publishedprojects.all()]:
            raise forms.ValidationError('Please specify a new unused version.')
        return data


class DiscoveryForm(forms.ModelForm):
    """
    Add discovery information to the project
    """
    programming_languages = forms.ModelMultipleChoiceField(
        queryset=ProgrammingLanguage.objects.all().order_by('name'),
        widget=forms.SelectMultiple(attrs={'size':'10'}),
        help_text='The programming languages used. Hold ctrl to select multiple. If your language is not listed here, <a href=/about>contact us</a>.',
        required=False)
    parent_projects = forms.ModelMultipleChoiceField(
        queryset=PublishedProject.objects.all().order_by(Lower('title'),
        'version_order'), widget=autocomplete.ModelSelect2Multiple(url='project-autocomplete'),
        help_text=f'The existing {settings.SITE_NAME} project(s) this '
                  f'resource was derived from. Hold ctrl to select multiple.',
        required=False)

    class Meta:
        model = ActiveProject
        fields = ('version', 'short_description', 'project_home_page', 'parent_projects',
            'programming_languages')
        help_texts = {
            'version':
            "* The version number of the resource. <a href=https://semver.org/ target=_blank>Semantic versioning</a> is encouraged. If unsure, put '1.0.0'.",
            'short_description':
            '* A brief description (at most 250 characters) of the project. '
            'This should be one or two complete sentences, and describe the '
            'contents of the project to a reader who is generally '
            'knowledgeable about the subject but is not specifically familiar '
            'with your research.',
            'project_home_page': 'External home page for the project.'
        }
        widgets = {'short_description':forms.Textarea(attrs={'rows':'4'})}

    def __init__(self, resource_type, editable=True, **kwargs):
        super().__init__(**kwargs)
        if resource_type != 1:
            del(self.fields['programming_languages'])

        if not editable:
            for f in self.fields.values():
                f.disabled = True

    def clean_short_description(self):
        data = self.cleaned_data['short_description']
        return ' '.join(data.split())

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        self.instance.content_modified()
        return result


class AffiliationFormSet(forms.BaseInlineFormSet):
    """
    Formset for adding an author's affiliations
    """
    form_name = 'affiliations'
    item_label = 'Affiliations'
    max_forms = Affiliation.MAX_AFFILIATIONS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_forms = AffiliationFormSet.max_forms
        self.help_text = 'Institutions you are affiliated with. Maximum of {}.'.format(self.max_forms)

    def clean(self):
        """
        - Check max forms due to POST refresh issue
        - validate unique_together values because generic relations
          don't automatically check).
        """
        if any(self.errors):
            return

        if len(set([a.id for a in self.instance.affiliations.all()]
                   + [f.instance.id for f in self.forms])) > self.max_forms:
            raise forms.ValidationError('Maximum number of allowed items exceeded.')

        names = []
        for form in self.forms:
            # This is to allow empty unsaved form
            if 'name' in form.cleaned_data:
                name = form.cleaned_data['name']
                if name in names:
                    raise forms.ValidationError('Affiliation names must be unique.')
                names.append(name)


class ReferenceFormSet(BaseGenericInlineFormSet):
    """
    Formset for adding a ActiveProject's references
    """
    form_name = 'project-reference-content_type-object_id'
    item_label = 'References'
    max_forms = 50

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_forms = ReferenceFormSet.max_forms
        self.help_text = 'Numbered references specified in the metadata. Article citations must be in <a href=http://www.bibme.org/citation-guide/apa/ target=_blank>APA</a> format. Maximum of {}.'.format(self.max_forms)

    def clean(self):
        """
        - Check max forms due to POST refresh issue
        - validate unique_together values because generic relations
          don't automatically check).
        """
        if any(self.errors):
            return

        if len(set([r.id for r in self.instance.references.all()]
                   + [f.instance.id for f in self.forms])) > self.max_forms:
            raise forms.ValidationError('Maximum number of allowed items exceeded.')

        descriptions = []
        for form in self.forms:
            # This is to allow empty unsaved form
            if 'description' in form.cleaned_data:
                description = form.cleaned_data['description']
                if description in descriptions:
                    raise forms.ValidationError('References must be unique.')
                descriptions.append(description)

    def save(self, *args, **kwargs):
        # change the value of order. set it as index of form
        for form in self.forms:
            form.instance.order = self.forms.index(form) + 1
        super().save(*args, **kwargs)


class PublicationFormSet(BaseGenericInlineFormSet):
    """
    Formset for adding a ActiveProject's publication
    """
    form_name = 'project-publication-content_type-object_id'
    item_label = 'Publication'
    max_forms = 1


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_forms = PublicationFormSet.max_forms
        self.help_text = ('The article publication to be cited, alongside this '
                          'resource, in <a href=http://www.bibme.org/citation-guide/apa/ '
                          'target=_blank>APA</a> format. If the article is in '
                          'press, leave the URL blank and contact us to update '
                          'it once it is available. Maximum of {}.').format(self.max_forms)

    def clean(self):
        """
        - Check max forms due to POST refresh issue
        """
        if any(self.errors):
            return

        if len(set([p.id for p in self.instance.publications.all()]
                   + [f.instance.id for f in self.forms])) > self.max_forms:
            raise forms.ValidationError('Maximum number of allowed items exceeded.')


class TopicFormSet(BaseGenericInlineFormSet):
    """
    Formset for adding a ActiveProject's topics
    """
    form_name = 'project-topic-content_type-object_id'
    item_label = 'Topics'
    max_forms = 20

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_forms = TopicFormSet.max_forms
        self.help_text = 'Keyword topics associated with the project. Increases the visibility of your project. Maximum of {}.'.format(self.max_forms)


class LanguageFormSet(BaseGenericInlineFormSet):
    """
    Formset for adding a ActiveProject's programming languages
    """
    form_name = 'project-programminglanguage-content_type-object_id'
    item_label = 'Programming Languages'
    max_forms = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_forms = LanguageFormSet.max_forms
        self.help_text = 'Programming languages used in this software. Maximum of {}.'.format(self.max_forms)

    def clean(self):
        """
        - Check max forms due to POST refresh issue
        - validate unique_together values because generic relations
          don't automatically check).
        """
        if any(self.errors):
            return

        if len(set([r.id for r in self.instance.languages.all()]
                   + [f.instance.id for f in self.forms])) > self.max_forms:
            raise forms.ValidationError('Maximum number of allowed items exceeded.')

        names = []
        for form in self.forms:
            # This is to allow empty unsaved form
            if 'name' in form.cleaned_data:
                name = form.cleaned_data['name']
                if name in names:
                    raise forms.ValidationError('Languages must be unique.')
                names.append(name)


class AccessMetadataForm(forms.ModelForm):
    class Meta:
        model = ActiveProject
        fields = ('access_policy', 'license', 'dua', 'required_trainings', 'allow_file_downloads')
        help_texts = {
            'access_policy': '* Access policy for files.',
            'license': "* License for usage. <a href='/about/publish/#licenses' target='_blank'>View available.</a>",
            'dua': "* Insert DUA help text!",
            'required_trainings': '* Choose required training to access the dataset.',
            'allow_file_downloads': (
                '* This option allows to enable/disable direct files downloads from the '
                'platform. It cannot be changed after the publication of the project!'
            ),
        }
        labels = {'dua': 'Data Use Agreement'}

    def __init__(self, *args, **kwargs):
        self.access_policy = kwargs.pop('access_policy', None)
        self.editable = kwargs.pop('editable', True)

        if self.access_policy is not None:
            kwargs.setdefault('initial', {}).update({'access_policy': self.access_policy})

        data = kwargs.get('data')
        if self.access_policy is None and data is not None:
            self.access_policy = int(data.get('access_policy'))

        super().__init__(*args, **kwargs)

        if not settings.ENABLE_FILE_DOWNLOADS_OPTION:
            del self.fields['allow_file_downloads']

        if self.access_policy is None:
            self.access_policy = self.instance.access_policy

        self.fields['license'].queryset = License.objects.filter(
            is_active=True,
            project_types=self.instance.resource_type,
            access_policy=self.access_policy
        )
        self.fields['dua'].queryset = DUA.objects.filter(
            is_active=True,
            project_types=self.instance.resource_type,
            access_policy=self.access_policy
        )

        if self.access_policy not in {AccessPolicy.CREDENTIALED, AccessPolicy.CONTRIBUTOR_REVIEW}:
            self.fields['required_trainings'].disabled = True
            self.fields['required_trainings'].required = False
            self.fields['required_trainings'].widget = forms.HiddenInput()
            self.initial['required_trainings'] = ''

        if self.access_policy == AccessPolicy.OPEN:
            self.fields['dua'].disabled = True
            self.fields['dua'].required = False
            self.fields['dua'].widget = forms.HiddenInput()
            self.initial['dua'] = ''

        if not self.editable:
            for field in self.fields.values():
                field.disabled = True


class AuthorCommentsForm(forms.Form):
    author_comments = forms.CharField(max_length=12000, required=False,
                                      label='Comments for editor (optional)',
                                      widget=forms.Textarea())


class InviteAuthorForm(forms.ModelForm):
    """
    Form to invite new authors to a project.
    Field to fill in: email.

    """
    def __init__(self, project, inviter, *args, **kwargs):
        super(InviteAuthorForm, self).__init__(*args, **kwargs)
        self.project = project
        self.inviter = inviter

    class Meta:
        model = AuthorInvitation
        fields = ('email',)

    def clean_email(self):
        "Ensure it is a fresh invite to a non-author"

        data = self.cleaned_data['email'].lower()

        for author in self.project.authors.all():
            if data in author.user.get_emails():
                raise forms.ValidationError(
                    'The user is already an author of this project',
                    code='already_author')

        invitations = self.project.authorinvitations.filter(is_active=True)

        if data in [i.email for i in invitations]:
            raise forms.ValidationError(
                'There is already an outstanding invitation to that email',
                code='already_invited')
        return data

    def save(self):
        invitation = super(InviteAuthorForm, self).save(commit=False)
        invitation.project = self.project
        invitation.inviter = self.inviter
        invitation.expiration_date = (timezone.now().date()
                                      + timezone.timedelta(days=21))
        invitation.save()
        return invitation


class StorageRequestForm(forms.ModelForm):
    """
    Making a request for storage capacity for a project.
    Request allowance is in GB
    """
    class Meta:
        model = StorageRequest
        # Storage request allowance in GB
        fields = ('request_allowance',)
        widgets = {'request_allowance': forms.NumberInput()}
        labels = {'request_allowance': 'Request allowance (GB)'}

    def __init__(self, project, *args, **kwargs):
        super(StorageRequestForm, self).__init__(*args, **kwargs)
        self.project = project

    def clean_request_allowance(self):
        """
        Storage size must be reasonable
        """
        data = self.cleaned_data['request_allowance']
        # Comparing GB form field to bytes model field
        if data * 1024 ** 3 <= self.project.core_project.storage_allowance:
            raise forms.ValidationError('Project already has the requested allowance.',
                code='already_has_allowance')

        return data

    def clean(self):
        """
        Must not have outstanding storage request
        """
        cleaned_data = super().clean()

        if self.project.storagerequests.filter(is_active=True):
            raise forms.ValidationError(
                  'This project already has an outstanding storage request.')
        return cleaned_data


class InvitationResponseForm(forms.ModelForm):
    """
    For responding to an author invitation
    """
    class Meta:
        model = AuthorInvitation
        fields = ('response',)
        widgets = {'response': forms.Select(choices=INVITATION_CHOICES)}

    affiliation = forms.CharField(max_length=Affiliation.MAX_LENGTH,
                                  validators=[validate_affiliation],
                                  label=('Your affiliation (displayed '
                                         'when the project is published)'),
                                  required=False)

    def clean(self):
        """
        Invitation must be active, user must be invited
        """
        cleaned_data = super().clean()
        if not self.instance.is_active:
            raise forms.ValidationError('Invalid invitation.')

        if self.instance.email not in self.user.get_emails():
            raise forms.ValidationError(
                  'You are not invited.')

        if cleaned_data['response'] and not cleaned_data.get('affiliation'):
            raise forms.ValidationError('You must specify your affiliation.')

        return cleaned_data

class AnonymousAccessLoginForm(forms.ModelForm):
    """
    Login for anonymous users
    """

    class Meta:
        model = AnonymousAccess
        fields = ('passphrase',)
        widgets = {
            'passphrase':forms.PasswordInput(attrs={'class': 'form-control',
                'placeholder': 'Passphrase', 'label': 'Passphrase'}),
        }


class DataAccessRequestForm(forms.ModelForm):
    class Meta:
        model = DataAccessRequest
        fields = ('data_use_title', 'data_use_purpose', 'agree_dua')
        help_texts = {
            'data_use_title': """Title of the project you would like to use the data for""",
            'data_use_purpose': """Detailed description of the data use.""",
        }
        labels = {
            'data_use_title': 'Research Project Title',
            'data_use_purpose': 'Research Project Details'
        }

    agree_dua = forms.BooleanField(required=True)

    def inline_fields(self):
        return [f for f in self.visible_fields() if
                f.field != self.fields['agree_dua']]

    def save(self):
        proj_request = super().save(commit=False)
        proj_request.project = self.project
        proj_request.requester = self.requester

        proj_request.save()
        return proj_request

    def __init__(self, project, requester, template, *args, **kwargs):
        kwargs.update(initial={
            'data_use_purpose': project.dua.access_template
        })

        super().__init__(*args, **kwargs)

        self.project = project
        self.requester = requester


class DataAccessResponseForm(forms.ModelForm):
    duration = forms.IntegerField(
        min_value=0, initial=14, label='Duration (in days)', help_text="If you enter 0, the access will not expire."
    )

    class Meta:
        model = DataAccessRequest
        fields = ('status', 'duration', 'responder_comments')
        help_texts = {
            'responder_comments': """Brief justification in case of rejection or comment for the requester""",
        }
        widgets = {
            'responder_comments': forms.Textarea(attrs={'rows': 3}),
            'status': forms.Select(choices=DataAccessRequest.REJECT_ACCEPT)
        }

        labels = {
            'status': 'Decision',
            'responder_comments': 'Comment or Justification'
        }

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data['status'] == DataAccessRequest.REJECT_REQUEST_VALUE and not cleaned_data['responder_comments']:
            raise forms.ValidationError('If you reject the request, you must state why.')

    def clean_duration(self):
        duration = self.cleaned_data['duration']
        if not duration:
            return None

        return timezone.timedelta(days=duration)

    def save(self):
        r = super().save(commit=False)
        r.decision_datetime = timezone.now()
        r.responder = self.responder
        r.save()

        return r

    def __init__(self, responder, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.responder = responder


class InviteDataAccessReviewerForm(forms.ModelForm):
    reviewer = forms.CharField(widget=forms.TextInput(
        attrs={'class': 'form-control'}),
        required=True, label=f'{settings.SITE_NAME} Username')

    class Meta:
        model = DataAccessRequestReviewer
        fields = ('reviewer',)

    def __init__(self, project, *args, **kwargs):
        super(InviteDataAccessReviewerForm, self).__init__(*args, **kwargs)
        self.project = project

    def clean_reviewer(self):
        reviewer_uname = self.cleaned_data['reviewer']
        try:
            reviewer = User.objects.get(username=reviewer_uname)
            if self.project.can_approve_requests(reviewer):
                raise forms.ValidationError(
                    f'User {reviewer_uname} is already allowed to review requests!')
        except User.DoesNotExist:
            raise forms.ValidationError(
                f'No user {reviewer_uname} found!', code='user_not_found')

        return reviewer

    def save(self):
        if self.errors:
            return

        reviewer = self.cleaned_data['reviewer']

        invitation = DataAccessRequestReviewer()
        if DataAccessRequestReviewer.objects.filter(reviewer=reviewer,
                                                    project=self.project).exists():
            # updating existing row in case a revoked user gets readded again
            invitation = DataAccessRequestReviewer.objects.get(
                reviewer=reviewer,
                project=self.project)
        else:
            invitation.reviewer = reviewer
            invitation.project = self.project

        invitation.is_revoked = False
        invitation.added_date = timezone.now()
        invitation.save()
        return invitation


class CustomClearableFileInput(forms.ClearableFileInput):
    template_name = 'project/custom_clearable_file_input.html'
    initial_text = 'Current file'
    clear_checkbox_label = 'Remove file'


class EthicsForm(forms.ModelForm):
    class Meta:
        model = ActiveProject
        fields = ('ethics_statement',)
        help_texts = {
            'ethics_statement': (
                '* A statement regarding ethical concerns for the work. '
                'This statement will be published with the resource, '
                'and typically describes formal approvals acquired for '
                'the creation of the resource (such as a review by an ethics board) '
                'for users of the resource. If no concerns, please indicate '
                'this 	&ldquo;The authors declare no ethics concerns&rdquo;.'
            ),
        }

    def __init__(self, editable=True, **kwargs):
        super().__init__(**kwargs)

        if not editable:
            for field in self.fields.values():
                field.disabled = True


class UploadedDocumentForm(forms.ModelForm):
    class Meta:
        model = UploadedDocument
        fields = (
            'document_type',
            'document',
        )
        widgets = {'document': CustomClearableFileInput}


class UploadedDocumentFormSet(BaseGenericInlineFormSet):
    form_name = 'project-uploadeddocument-content_type-object_id'
    item_label = 'Supporting Documents'
    max_forms = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        url = f"{reverse_lazy('static_view', kwargs={'static_url':'publish'} )}#author_guidelines"
        self.help_text = (
            "Please provide an ethics statement following the "
            f"<a href='{url}' target='_blank'>author guidelines</a>. "
            "Statements on ethics approval should appear here. "
            "Your statement will be included in the public project description."
        )
