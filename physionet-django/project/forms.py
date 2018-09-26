import os
import pdb
import re

from django import forms
from django.contrib.contenttypes.forms import BaseGenericInlineFormSet
# from django.forms import , Select, Textarea
from django.template.defaultfilters import slugify
from django.utils import timezone

from .models import Affiliation, Author, Invitation, Project, StorageRequest
from . import utility


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


class ProjectFilesForm(forms.Form):
    """
    Inherited form for manipulating project files/directories. Upload
    and create folders, move, rename, delete items.
    """
    # The working subdirectory relative to the project root
    subdir = forms.CharField(widget=forms.HiddenInput(), required=False)

    def __init__(self, project, *args, **kwargs):
        super(ProjectFilesForm, self).__init__(*args, **kwargs)
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


class UploadFilesForm(ProjectFilesForm):
    """
    Form for uploading multiple files to a project.
    `subdir` is the project subdirectory relative to the file root.
    """
    file_field = forms.FileField(widget=forms.ClearableFileInput(
        attrs={'multiple': True}), required=False)

    def clean_file_field(self):
        """
        Check for file size limits and whether they are readable
        """
        files = self.files.getlist('file_field')

        for file in files:
            if re.match(r'(?u)[^-\w.]', file.name):
                raise forms.ValidationError('Invalid characters in file, allowed ' \
                    'characters are: numbers, letters, dash, underscore, or dot: %(file_name)s',
                    params={'file_name':file.name})
            # Special error
            if not file:
                raise forms.ValidationError('Could not read file: %(file_name)s',
                    params={'file_name':file.name})

        for file in files:
            if file.size > Project.INDIVIDUAL_FILE_SIZE_LIMIT:
                raise forms.ValidationError(
                    'File %(file_name)s is larger than the individual size limit: %(individual_size_limit)s',
                    code='exceed_individual_limit',
                    params={'file_name':file.name,
                            'individual_size_limit':utility.readable_size(Project.INDIVIDUAL_FILE_SIZE_LIMIT)}
                )

        if sum(f.size for f in files) > self.project.storage_allowance*1024**3 - self.project.storage_used():
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


class CreateFolderForm(ProjectFilesForm):
    """
    Form for creating a new folder in a directory
    """
    folder_name = forms.CharField(max_length=50, required=False)
    def clean_folder_name(self):
        data = self.cleaned_data['folder_name']
        if re.match(r'(?u)[^-\w.]', data):
            raise forms.ValidationError('Invalid characters in folder name, allowed ' \
                'characters are: numbers, letters, dash, underscore, or dot: %(illegal_pattern)s',
                params={'illegal_pattern':data})
        return data

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


class EditItemsForm(ProjectFilesForm):
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
    new_name = forms.CharField(max_length=50, required=False)

    field_order = ['subdir', 'items', 'new_name']


    def clean_new_name(self):
        """
        - Prevent renaming to an already taken name in the current directory.
        - Prevent illegal names
        """
        data = self.cleaned_data['new_name']
        taken_names = utility.list_items(self.file_dir, return_separate=False)

        if re.match(r'(?u)[^-\w.]', data):
            raise forms.ValidationError('Invalid characters in filename, allowed ' \
                'characters are: numbers, letters, dash, underscore, or dot: %(file_name)s',
                params={'file_name':data})

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
        super(CreateProjectForm, self).__init__(*args, **kwargs)
        self.user = user

    class Meta:
        model = Project
        fields = ('resource_type', 'title', 'abstract',)

    def clean(self):
        """
        Check that the title and resource type are unique for the user.
        Needs to be run because submitting_author is not a form field.
        """
        cleaned_data = super().clean()
        if Project.objects.filter(resource_type=cleaned_data['resource_type'],
                                  title=cleaned_data['title'],
                                  submitting_author=self.user).exists():
            raise forms.ValidationError(
                  'You already have a project with this title and resource type')
        return cleaned_data

    def save(self):
        project = super(CreateProjectForm, self).save(commit=False)
        project.submitting_author = self.user
        project.corresponding_author = self.user
        project.save()
        return project


class DatabaseMetadataForm(forms.ModelForm):
    """
    Form for editing the metadata of a project with resource_type == database
    """
    class Meta:
        model = Project
        fields = ('title', 'abstract', 'background', 'methods',
                  'content_description', 'usage_notes', 'acknowledgements',
                  'conflicts_of_interest', 'version', 'changelog_summary',)
        help_texts = {'title': '* Title of the resource.',
                      'abstract': '* A brief description of the resource and the context in which the resource was created.',
                      'background': '* The study background.',
                      'methods': '* The methodology employed for the study or research. Describe how the data was collected. If your project has an external home page, you should include it here.',
                      'content_description': '* Describe the files, how they are named and structured, and how they are to be used.',
                      'usage_notes': 'How the data is to be used. List any related software developed for the dataset, and any special software required to use the data.',
                      'acknowledgements': 'Any general acknowledgements.',
                      'conflicts_of_interest': '* Conflicts of interest of any authors. State explicitly if there are none.',
                      'version': '* The version number of the resource. <a href=https://semver.org/ target=_blank>Semantic versioning</a> is encouraged (example: 1.0.0).',
                      'changelog_summary': '* Summary of changes from the previous release.'}

    def __init__(self, include_changelog=False, *args, **kwargs):
        super(DatabaseMetadataForm, self).__init__(*args, **kwargs)
        if not include_changelog:
            del(self.fields['changelog_summary'])

        self.fields['content_description'].label = 'Data description'


    def clean_title(self):
        """
        Check that the title and resource type are unique for the user
        """
        data = self.cleaned_data['title']

        if Project.objects.filter(
                title=data,
                resource_type=self.instance.resource_type,
                submitting_author=self.instance.submitting_author).exclude(id=self.instance.id).exists():
            raise forms.ValidationError(
                  'You already have a project with this title and resource type')

        return data


class SoftwareMetadataForm(forms.ModelForm):
    """
    Form for editing the metadata of a project with resource_type == database
    NOT DONE
    """
    class Meta:
        model = Project
        fields = ('title', 'abstract', 'usage_notes')


# The modelform for editing metadata for each resource type
METADATA_FORMS = {0: DatabaseMetadataForm,
                  1: SoftwareMetadataForm}


class AffiliationFormSet(BaseGenericInlineFormSet):
    """
    Formset for adding an author's affiliations
    """
    form_name = 'project-affiliation-content_type-object_id'
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
    Formset for adding a Project's references
    """
    form_name = 'project-reference-content_type-object_id'
    item_label = 'References'
    max_forms = 20

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
    Formset for adding a Project's publication
    """
    form_name = 'project-publication-content_type-object_id'
    item_label = 'Publication'
    max_forms = 1


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_forms = PublicationFormSet.max_forms
        self.help_text = 'The article publication to be cited, alongside this resource, in <a href=http://www.bibme.org/citation-guide/apa/ target=_blank>APA</a> format. If the article is in press, leave the URL blank and contact us to update it once it is available. Maximum of {}.'.format(self.max_forms)

    def clean(self):
        """
        - Check max forms due to POST refresh issue
        """
        if any(self.errors):
            return

        if len(set([p.id for p in self.instance.publications.all()]
                   + [f.instance.id for f in self.forms])) > self.max_forms:
            raise forms.ValidationError('Maximum number of allowed items exceeded.')


class TopicFormSet(forms.BaseInlineFormSet):
    """
    Formset for adding a Project's topics
    """
    form_name = 'topics'
    item_label = 'Topics'
    max_forms = 20

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_forms = TopicFormSet.max_forms
        self.help_text = 'Keyword topics associated with the project. Increases the visibility of your project. Maximum of {}.'.format(self.max_forms)


class AccessMetadataForm(forms.ModelForm):
    """
    For editing project access metadata
    """
    class Meta:
        model = Project
        fields = ('access_policy', 'license', 'data_use_agreement')
        help_texts = {'access_policy': '* Access policy for files.',
                      'license': '* License for usage',
                      'data_use_agreement': 'Specific conditions for usage'}

    def clean(self):
        """
        Check the combination of access policy and dua
        """
        cleaned_data = super().clean()
        if cleaned_data['access_policy'] == 0 and cleaned_data['data_use_agreement'] is not None:
            raise forms.ValidationError('Open-acess projects cannot have DUAs')
        return cleaned_data


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
        model = Invitation
        fields = ('email',)

    def clean_email(self):
        "Ensure it is a fresh invite to a non-author"
        data = self.cleaned_data['email']

        for author in self.project.authors.filter(is_human=True):
            if data in author.user.get_emails():
                raise forms.ValidationError(
                    'The user is already an author of this project',
                    code='already_author')

        invitations = self.project.invitations.filter(
            invitation_type='author', is_active=True)

        if data in [i.email for i in invitations]:
            raise forms.ValidationError(
                'There is already an outstanding invitation to that email',
                code='already_invited')
        return data

    def save(self):
        invitation = super(InviteAuthorForm, self).save(commit=False)
        invitation.project = self.project
        invitation.inviter = self.inviter
        invitation.invitation_type = 'author'
        invitation.expiration_date = (timezone.now().date()
            + timezone.timedelta(days=21))
        invitation.save()
        return invitation


class AddAuthorForm(forms.ModelForm):
    """
    Add a non-human author
    """
    class Meta:
        model = Author
        fields = ('organization_name',)

    def __init__(self, project, *args, **kwargs):
        "Make sure the user submitting this entry is the owner"
        super(AddAuthorForm, self).__init__(*args, **kwargs)
        self.project = project

    def clean_organization_name(self):
        """
        Ensure uniqueness of organization name
        """
        data = self.cleaned_data['organization_name']
        if self.project.authors.filter(organization_name=data).exists():
            raise forms.ValidationError('Organizational author names must be unique')

        return data

    def save(self):
        author = super(AddAuthorForm, self).save(commit=False)
        author.project = self.project
        author.is_human = False
        author.display_order = self.project.authors.count() + 1
        author.save()


class StorageRequestForm(forms.ModelForm):
    """
    Making a request for storage capacity for a project
    """
    class Meta:
        model = StorageRequest
        # Storage request allowance in GB
        fields = ('request_allowance',)
        widgets = {
            'request_allowance':forms.NumberInput(),
        }

    def __init__(self, project, *args, **kwargs):
        super(StorageRequestForm, self).__init__(*args, **kwargs)
        self.project = project

    def clean_request_allowance(self):
        """
        Storage size must be reasonable
        """
        data = self.cleaned_data['request_allowance']

        if data <= self.project.storage_allowance:
            raise forms.ValidationError('Project already has the requested allowance.',
                code='already_has_allowance')

        return data

    def clean(self):
        """
        Must not have outstanding storage request
        """
        cleaned_data = super().clean()

        if self.project.storage_requests.filter(is_active=True):
            raise forms.ValidationError(
                  'This project already has an outstanding storage request.')
        return cleaned_data


class InvitationResponseForm(forms.ModelForm):
    """
    For responding to an author invitation
    """
    class Meta:
        model = Invitation
        fields = ('response', 'response_message')
        widgets={'response':forms.Select(choices=RESPONSE_CHOICES),
                 'response_message':forms.Textarea()}

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
