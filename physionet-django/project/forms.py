from collections import OrderedDict
import os
import pdb
import re

from django import forms
from django.contrib.contenttypes.forms import BaseGenericInlineFormSet
from django.template.defaultfilters import slugify
from django.utils import timezone
from django.utils.crypto import get_random_string

from .models import (Affiliation, Author, AuthorInvitation, ActiveProject,
    CoreProject, StorageRequest, ProgrammingLanguage, License, Metadata,
    Reference, Publication, Topic, exists_project_slug)
from . import utility
from . import validators


RESPONSE_CHOICES = (
    (1, 'Accept'),
    (0, 'Reject')
)

class CorrespondingAuthorForm(forms.Form):
    """
    Select a corresponding author for a project
    """
    author = forms.ModelChoiceField(queryset=None)

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        project_authors = project.authors.all()
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


class ActiveProjectFilesForm(forms.Form):
    """
    Inherited form for manipulating project files/directories. Upload
    and create folders, move, rename, delete items.
    """
    # The working subdirectory relative to the project root
    subdir = forms.CharField(widget=forms.HiddenInput(), required=False)

    def __init__(self, project, *args, **kwargs):
        super(ActiveProjectFilesForm, self).__init__(*args, **kwargs)
        self.project = project

    def clean_subdir(self):
        """
        Check that the subdirectory exists
        """
        data = self.cleaned_data['subdir']
        file_dir = os.path.join(self.project.file_root(), data)

        if not os.path.isdir(file_dir):
            raise forms.ValidationError('Invalid directory')
        self.file_dir = file_dir

        return data


class UploadFilesForm(ActiveProjectFilesForm):
    """
    Form for uploading multiple files to a project.
    `subdir` is the project subdirectory relative to the file root.
    """
    file_field = forms.FileField(widget=forms.ClearableFileInput(
        attrs={'multiple': True}), required=False, allow_empty_file=True)

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
                    params={'file_name':file.name})

        for file in files:
            if file.size > ActiveProject.INDIVIDUAL_FILE_SIZE_LIMIT:
                raise forms.ValidationError(
                    'File %(file_name)s is larger than the individual size limit: %(individual_size_limit)s',
                    code='exceed_individual_limit',
                    params={'file_name':file.name,
                            'individual_size_limit':utility.readable_size(ActiveProject.INDIVIDUAL_FILE_SIZE_LIMIT)}
                )

        if sum(f.size for f in files) > self.project.core_project.storage_allowance - self.project.storage_used():
            raise forms.ValidationError(
                'Total upload volume exceeds remaining quota',
                code='exceed_remaining_quota',
            )
        return files

    def clean(self):
        """
        Check for name clash with existing files/folders in the directory
        """
        if self.errors: return

        files = self.files.getlist('file_field')

        self.taken_names = utility.list_items(self.file_dir, return_separate=False)

        for file in files:
            if file.name in self.taken_names:
                raise forms.ValidationError('Item named: "%(taken_name)s" already exists in current folder.',
                    code='clashing_name', params={'taken_name':file.name})

    def perform_action(self):
        """
        Upload the files
        """
        for file in self.files.getlist('file_field'):
            utility.write_uploaded_file(file=file,
                write_file_path=os.path.join(self.file_dir, file.name))
        return 'Your files have been uploaded'


class CreateFolderForm(ActiveProjectFilesForm):
    """
    Form for creating a new folder in a directory
    """
    folder_name = forms.CharField(max_length=50, required=False,
        validators=[validators.validate_filename])

    def clean(self):
        """
        Check for name clash with existing files/folders in the directory
        """
        if self.errors: return

        folder_name = self.cleaned_data['folder_name']
        self.taken_names = utility.list_items(self.file_dir, return_separate=False)

        if folder_name in self.taken_names:
            raise forms.ValidationError('Item named: "%(taken_name)s" already exists in current folder.',
                code='clashing_name', params={'taken_name':folder_name})

    def perform_action(self):
        """
        Create the folder
        """
        os.mkdir(os.path.join(self.file_dir, self.cleaned_data['folder_name']))
        return 'Your folder has been created'


class EditItemsForm(ActiveProjectFilesForm):
    """
    Inherited form for manipulating existing files/directories.
    Rename, edit, delete. This is also the form for deleting items.

    """
    # This field's choices depend on the `subdir` field
    items = forms.MultipleChoiceField()

    field_order = ['subdir', 'items']

    def clean_subdir(self, *args, **kwargs):
        """
        Set the items' valid choices after cleaning the subdirectory.
        This must be called before clean_items.
        """
        super(EditItemsForm, self).clean_subdir(*args, **kwargs)
        existing_items = utility.list_items(self.file_dir, return_separate=False)
        self.fields['items'].choices = tuple((item, item) for item in existing_items)
        return self.cleaned_data['subdir']

    def perform_action(self):
        """
        Delete the items
        """
        utility.remove_items([os.path.join(self.file_dir, i) for i in self.cleaned_data['items']])
        return 'Your items have been deleted'


class RenameItemForm(EditItemsForm):
    """
    Form for renaming an item in a directory
    """
    # The name is 'items' to override the parent class field.
    items = forms.ChoiceField(required=False)
    new_name = forms.CharField(max_length=50, required=False,
        validators=[validators.validate_filename])

    field_order = ['subdir', 'items', 'new_name']


    def clean_new_name(self):
        """
        - Prevent renaming to an already taken name in the current directory.
        - Prevent illegal names
        """
        data = self.cleaned_data['new_name']
        taken_names = utility.list_items(self.file_dir, return_separate=False)

        if data in taken_names:
            raise forms.ValidationError('Item named: "%(taken_name)s" already exists in current folder.',
                code='clashing_name', params={'taken_name':data})

        return data

    def perform_action(self):
        """
        Rename the items
        """
        os.rename(os.path.join(self.file_dir, self.cleaned_data['items']),
            os.path.join(self.file_dir, self.cleaned_data['new_name']))
        return 'Your item has been renamed'



class MoveItemsForm(EditItemsForm):
    """
    Form for moving items into a target folder
    """
    destination_folder = forms.ChoiceField(required=False)

    field_order = ['subdir', 'items', 'destination_folder']

    def __init__(self, project, subdir=None, *args, **kwargs):
        """
        Set the choices for the destination folder
        """
        super(MoveItemsForm, self).__init__(project, *args, **kwargs)
        # The choices are only set here for get requests
        if subdir is not None:
            self.fields['destination_folder'].choices = MoveItemsForm.get_destination_choices(
                project, subdir)

    def get_destination_choices(project, subdir):
        """
        Return allowed destination choices
        """
        existing_subdirs = utility.list_directories(
            os.path.join(project.file_root(), subdir))
        subdir_choices = [(s, s) for s in existing_subdirs]
        if subdir:
            subdir_choices = [('../', '*Parent Directory*')] + subdir_choices
        return subdir_choices

    def clean_subdir(self, *args, **kwargs):
        """
        Set the allowed destination choices after the subdir is cleaned
        """
        super(MoveItemsForm, self).clean_subdir(*args, **kwargs)
        data = self.cleaned_data['subdir']
        self.fields['destination_folder'].choices = MoveItemsForm.get_destination_choices(
            self.project, data)
        return data

    def clean(self):
        """
        Selected destination folder:
        - Must not be one of the items selected to be moved
        - Must not contain items with the same name as the items to be moved

        """
        cleaned_data = super(MoveItemsForm, self).clean()
        validation_errors = []

        destination_folder = cleaned_data['destination_folder']
        selected_items = cleaned_data['items']

        if destination_folder in selected_items:
            validation_errors.append(forms.ValidationError('Cannot move folder: %(destination_folder)s into itself',
                code='move_folder_self',
                params={'destination_folder':destination_folder}))

        taken_names = utility.list_items(os.path.join(self.file_dir, destination_folder),
            return_separate=False)
        clashing_names = set(selected_items).intersection(set(taken_names))

        if clashing_names:
            validation_errors.append(forms.ValidationError('Item named: "%(clashing_name)s" already exists in destination folder.',
                code='clashing_name', params={'clashing_name':list(clashing_names)[0]}))

        if validation_errors:
            raise forms.ValidationError(validation_errors)


    def perform_action(self):
        """
        Move the items into the selected directory
        """
        utility.move_items([os.path.join(self.file_dir, i) for i in self.cleaned_data['items']],
            os.path.join(self.file_dir, self.cleaned_data['destination_folder']))
        return 'Your items have been moved'


class CreateProjectForm(forms.ModelForm):
    """
    For creating projects
    """
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    class Meta:
        model = ActiveProject
        fields = ('resource_type', 'title', 'abstract',)

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
        os.mkdir(project.file_root())
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
        # Direct copy over fields
        for attr in [f.name for f in Metadata._meta.fields]:
            if attr not in ['slug', 'version', 'creation_datetime']:
                setattr(project, attr, getattr(self.latest_project, attr))
        # Set new fields
        slug = get_random_string(20)
        while exists_project_slug(slug):
            slug = get_random_string(20)
        project.slug = slug
        project.creation_datetime = timezone.now()
        project.version_order = self.latest_project.version_order + 1
        project.is_new_version = True
        project.save()

        # Copy over the author/affiliation objects
        for p_author in self.latest_project.authors.all():
            author = Author.objects.create(project=project, user=p_author.user,
                display_order=p_author.display_order,
                is_submitting=p_author.is_submitting,
                is_corresponding=p_author.is_corresponding,
                corresponding_email=self.user.get_primary_email(),)

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

        for p_topic in self.latest_project.topics.all():
            topic = Topic.objects.create(project=project,
                description=p_topic.description)

        # Create file directory
        os.mkdir(project.file_root())
        current_file_root = project.file_root()
        older_file_root = self.latest_project.file_root()
        files = utility.get_tree_files(older_file_root, full_path=False)
        for file in files:
            destination = os.path.join(current_file_root, file)
            if not os.path.exists(os.path.dirname(destination)):
                try:
                    os.makedirs(os.path.dirname(destination))
                except OSError as exc: # Guard against race condition
                    if exc.errno != errno.EEXIST:
                        raise
            os.link(os.path.join(older_file_root, file),  destination)

        return project


class MetadataForm(forms.ModelForm):
    """
    Form for editing the metadata of a project.
    Fields, labels, and help texts may be defined differently for
    different resource types.

    """

    FIELDS = (
        # 0: Database
        ('title', 'abstract', 'background', 'methods', 'content_description',
         'usage_notes', 'version', 'release_notes', 'acknowledgements',
         'conflicts_of_interest',
         ),
        # 1: Software
        ('title', 'abstract', 'background', 'content_description',
         'methods', 'installation', 'usage_notes', 'version', 'release_notes',
         'acknowledgements', 'conflicts_of_interest', ),
        # 2: Challenge
        ('title', 'abstract', 'background', 'methods', 'content_description',
         'usage_notes', 'version', 'release_notes', 'acknowledgements',
         'conflicts_of_interest',
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
    )

    class Meta:
        model = ActiveProject
        # This includes fields for all resource types.
        fields = ('title', 'abstract', 'background', 'methods',
                  'content_description', 'installation', 'usage_notes',
                  'acknowledgements', 'conflicts_of_interest',
                  'version', 'release_notes',)

        help_texts = {
            'title': '* The title of the resource.',
            'abstract': '* A brief description of the resource and the context in which it was created.',
            'background': '* The content or research background.',
            'installation': '* Instructions on how to install the software, along with the required dependencies. Or specify the files in which they are listed.',
            'acknowledgements': 'Thank the people who helped with the research but did not qualify for authorship. In addition, provide any funding information.',
            'conflicts_of_interest': '* List whether any authors have a financial, commercial, legal, or professional relationship with other organizations, or with the people working with them, that could influence this research. State explicitly if there are none.',
            'version': "* The version number of the resource. <a href=https://semver.org/ target=_blank>Semantic versioning</a> is encouraged. If unsure, put '1.0.0'.",
            'release_notes': 'Important notes about the current release, and changes from previous versions.'
        }

    def __init__(self, resource_type, *args, **kwargs):
        super(MetadataForm, self).__init__(*args, **kwargs)
        self.fields = OrderedDict((k, self.fields[k]) for k in self.FIELDS[resource_type])

        for l in ActiveProject.LABELS[resource_type]:
            self.fields[l].label = ActiveProject.LABELS[resource_type][l]

        for h in self.__class__.HELP_TEXTS[resource_type]:
            self.fields[h].help_text = self.__class__.HELP_TEXTS[resource_type][h]

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
        help_text='The programming languages used. Hold ctrl to select multiple. If your language is not listed here, <a href=/about>contact us</a>.')

    class Meta:
        model = ActiveProject
        fields = ('short_description', 'project_home_page', 'programming_languages')
        help_texts = {
            'project_home_page': 'External home page for the project.',
            'short_description': 'Short (maximum 250 character) description of the project.'
        }

    def __init__(self, resource_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if resource_type != 1:
            del(self.fields['programming_languages'])


class AffiliationFormSet(forms.BaseInlineFormSet):
    """
    Formset for adding an author's affiliations
    """
    form_name = 'affiliations'
    item_label = 'Affiliations'
    max_forms = 3

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
    """
    For editing project access metadata
    """
    class Meta:
        model = ActiveProject
        fields = ('access_policy', 'license')
        help_texts = {'access_policy': '* Access policy for files.',
                      'license': "* License for usage. <a href='/about/publish/#licenses' target='_blank'>View available.</a>"}

    def __init__(self, *args, **kwargs):
        """
        Control the available access policies based on the existing
        licenses. The license queryset is set in the following
        `set_license_queryset` function.

        Each license has one access policy, and potentially multiple
        resource types.
        """
        super().__init__(*args, **kwargs)

        # Get licenses for this resource type
        licenses = License.objects.filter(
            resource_types__icontains=str(self.instance.resource_type))
        # Set allowed access policies based on license policies
        available_policies = [a for a in range(len(Metadata.ACCESS_POLICIES)) if licenses.filter(access_policy=a)]
        self.fields['access_policy'].choices = tuple(Metadata.ACCESS_POLICIES[p] for p in available_policies)

    def set_license_queryset(self, access_policy):
        """
        Set the license queryset according to the set or selected
        access policy.
        """
        self.fields['license'].queryset = License.objects.filter(
            resource_types__icontains=str(self.instance.resource_type),
            access_policy=access_policy)

    def clean(self):
        """
        Ensure valid license access policy combinations
        """
        data = super().clean()
        if (str(self.instance.resource_type) in data['license'].resource_types
                and data['access_policy'] == data['license'].access_policy):
            return data

        raise forms.ValidationError('Invalid policy license combination.')


class AuthorCommentsForm(forms.Form):
    author_comments = forms.CharField(max_length=12000, required=False,
        label='Comments for editor (optional)', widget=forms.Textarea())


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
        data = self.cleaned_data['email']

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
        widgets = {'request_allowance':forms.NumberInput()}
        labels = {'request_allowance':'Request allowance (GB)'}

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
        widgets = {'response':forms.Select(choices=RESPONSE_CHOICES)}

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

        return cleaned_data
