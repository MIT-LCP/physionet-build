from django import forms
from django.forms import BaseInlineFormSet
from django.template.defaultfilters import slugify
from django.utils import timezone
import os

from .models import Affiliation, Author, Invitation, Project, StorageRequest
from .utility import readable_size, list_items, list_directories
import pdb


illegal_patterns = ['/','..',]


class MultiFileFieldForm(forms.Form):
    """
    Form for uploading multiple files
    """
    file_field = forms.FileField(widget=forms.ClearableFileInput(
        attrs={'multiple': True}))

    def __init__(self, individual_size_limit, total_size_limit,
                 current_directory, *args, **kwargs):
        # Email choices are those belonging to a user
        super(MultiFileFieldForm, self).__init__(*args, **kwargs)
        self.individual_size_limit = individual_size_limit
        self.total_size_limit = total_size_limit
        self.current_directory = current_directory

    def clean_file_field(self):
        """
        Check for file size limits and prevent upload when existing
        file/folder exists in directory
        """
        # Prospective upload content
        data = self.cleaned_data['file_field']
        files = self.files.getlist('file_field')

        self.taken_names = list_items(self.current_directory,
                                      return_separate=False)

        total_size = 0
        for file in files:
            if file:
                if file.size > self.individual_size_limit:
                    raise forms.ValidationError(
                        'File: "%(file_name)s" exceeds individual size limit: %(individual_size_limit)s',
                        code='exceed_individual_limit',
                        params={'file_name':file.name, 'individual_size_limit':readable_size(self.individual_size_limit)}
                    )
                total_size += file.size
                if total_size > self.total_size_limit:
                    raise forms.ValidationError(
                        'Total upload size exceeds limit: %(total_size_limit)s',
                        code='exceed_total_limit',
                        params={'total_size_limit':readable_size(self.total_size_limit)}
                    )
                if file.name in self.taken_names:
                    raise forms.ValidationError('Item named: "%(taken_name)s" already exists in current folder.',
                        code='clashing_name', params={'taken_name':file.name})
            else:
                # Special error
                raise forms.ValidationError('Could not read the uploaded file')

        return data


class FolderCreationForm(forms.Form):
    """
    Form for creating a new folder in a directory
    """
    folder_name = forms.CharField(max_length=50)

    def __init__(self, current_directory=None, *args, **kwargs):
        super(FolderCreationForm, self).__init__(*args, **kwargs)
        self.current_directory = current_directory

    def clean_folder_name(self):
        """
        Prevent upload when existing file/folder exists in directory
        """
        data = self.cleaned_data['folder_name']
        self.taken_names = list_items(self.current_directory, return_separate=False)

        if data in self.taken_names:
            raise forms.ValidationError('Item named: "%(taken_name)s" already exists in current folder.',
                code='clashing_name', params={'taken_name':data})

        for substring in illegal_patterns:
            if substring in data:
                raise forms.ValidationError('Illegal pattern specified in item name: "%(illegal_pattern)s"',
                code='illegal_pattern', params={'illegal_pattern':substring})

        return data


class RenameItemForm(forms.Form):
    """
    Form for renaming an item in a directory
    """
    new_name = forms.CharField(max_length=50)
    selected_item = forms.ChoiceField()

    def __init__(self, current_directory, *args, **kwargs):
        """
        Get the available items in the directory to rename, and set the form
        field's set of choices.
        """
        super(RenameItemForm, self).__init__(*args, **kwargs)
        self.current_directory = current_directory
        existing_items = list_items(current_directory, return_separate=False)
        self.fields['selected_item'].choices = [(i, i) for i in existing_items]

    def clean_selected_item(self):
        """
        Ensure selected item to rename exists in directory
        """
        data = self.cleaned_data['selected_item']
        existing_items = list_items(self.current_directory, return_separate=False)

        if data not in existing_items:
            raise forms.ValidationError('Invalid item selection.',
                code='invalid_item_selection')

        return data

    def clean_new_name(self):
        """
        - Prevent renaming to an already taken name in the current directory.
        - Prevent illegal names
        """
        data = self.cleaned_data['new_name']
        taken_names = list_items(self.current_directory, return_separate=False)

        if data in taken_names:
            raise forms.ValidationError('Item named: "%(taken_name)s" already exists in current folder.',
                code='clashing_name', params={'taken_name':data})

        for substring in illegal_patterns:
            if substring in data:
                raise forms.ValidationError('Illegal pattern specified in item name: "%(illegal_pattern)s"',
                code='illegal_pattern', params={'illegal_pattern':substring})

        return data


class MoveItemsForm(forms.Form):
    """
    Form for moving items into a target folder
    """
    destination_folder = forms.ChoiceField()
    selected_items = forms.MultipleChoiceField()

    def __init__(self, current_directory, in_subdir, *args, **kwargs):
        """
        Get the available items in the directory to move, the available
        target subdirectories, and set the two form fields' set of choices.
        """
        super(MoveItemsForm, self).__init__(*args, **kwargs)
        self.current_directory = current_directory
        self.in_subdir = in_subdir

        existing_files, existing_subdirectories = list_items(current_directory)
        existing_items = existing_files + existing_subdirectories

        destination_folder_choices = [(s, s) for s in existing_subdirectories]
        if in_subdir:
            destination_folder_choices = [('../', '*Parent Directory*')] + destination_folder_choices

        self.fields['destination_folder'].choices = destination_folder_choices
        self.fields['selected_items'].choices = [(i, i) for i in existing_items]

    def clean_selected_items(self):
        """
        Ensure selected items to move exist in directory
        """
        data = self.cleaned_data['selected_items']
        existing_items = list_items(self.current_directory, return_separate=False)

        if not set(data).issubset(set(existing_items)):
            raise forms.ValidationError('Invalid item selection.',
                code='invalid_item_selection')

        return data

    def clean_destination_folder(self):
        """
        Selected destination folderm ust exist in current directory

        """
        data = self.cleaned_data['destination_folder']
        existing_items = list_items(self.current_directory, return_separate=False)

        if data not in existing_items:
            raise forms.ValidationError('Invalid destination folder selection.',
                code='invalid_destination_selection')

        return data

    def clean(self):
        """
        Selected destination folder:
        - Must not be one of the items selected to be moved
        - Must not contain items with the same name as the items to be moved

        """
        cleaned_data = super().clean()
        validation_errors = []

        destination_folder = cleaned_data['destination_folder']
        selected_items = cleaned_data['selected_items']

        if destination_folder in selected_items:
            # raise forms.ValidationError('Cannot move folder: %(destination_folder)s into itself',
            #     code='move_folder_self',
            #     params={'destination_folder':destination_folder})

            validation_errors.append(forms.ValidationError('Cannot move folder: %(destination_folder)s into itself',
                code='move_folder_self',
                params={'destination_folder':destination_folder}))

        taken_names = list_items(os.path.join(self.current_directory, destination_folder),
            return_separate=False)
        clashing_names = set(selected_items).intersection(set(taken_names))

        if clashing_names:
            # raise forms.ValidationError('Item named: "%(clashing_name)s" already exists in destination folder.',
            #     code='clashing_name', params={'clashing_name':list(clashing_names)[0]})
            validation_errors.append(forms.ValidationError('Item named: "%(clashing_name)s" already exists in destination folder.',
                code='clashing_name', params={'clashing_name':list(clashing_names)[0]}))

        if validation_errors:
            raise forms.ValidationError(validation_errors)


class DeleteItemsForm(forms.Form):
    """
    Form for deleting items
    """
    selected_items = forms.MultipleChoiceField()

    def __init__(self, current_directory, *args, **kwargs):
        """
        Get the available items in the directory to delete, and set the form
        field's set of choices.
        """
        super(DeleteItemsForm, self).__init__(*args, **kwargs)
        self.current_directory = current_directory
        existing_items = list_items(current_directory, return_separate=False)
        self.fields['selected_items'].choices = [(i, i) for i in existing_items]

    def clean_selected_items(self):
        """
        Ensure selected items to delete exist in directory
        """
        data = self.cleaned_data['selected_items']
        existing_items = list_items(self.current_directory, return_separate=False)

        if not set(data).issubset(set(existing_items)):
            raise forms.ValidationError('Invalid item selection.',
                code='invalid_item_selection')

        return data


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
        project.save()
        return project


class DatabaseMetadataForm(forms.ModelForm):
    """
    Form for editing the metadata of a project with resource_type == database
    """
    class Meta:
        model = Project
        fields = ('title', 'abstract', 'background', 'methods',
            'content_description', 'acknowledgements',
            'version', 'changelog_summary',)

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
        fields = ('title', 'abstract', 'technical_validation', 'usage_notes')


# The modelform for editing metadata for each resource type
metadata_forms = {'Database':DatabaseMetadataForm,
                  'Software':SoftwareMetadataForm}


class AccessMetadataForm(forms.ModelForm):
    """
    For editing project access metadata
    """
    class Meta:
        model = Project
        fields = ('access_policy', 'license', 'data_use_agreement')

    def clean(self):
        """
        Check the combination of access policy and dua
        """
        cleaned_data = super().clean()
        if cleaned_data['access_policy'] == 0 and cleaned_data['data_use_agreement'] is not None:
            raise forms.ValidationError('Open-acess projects cannot have DUAs')
        return cleaned_data


class IdentifierMetadataForm(forms.ModelForm):
    """
    For editing project identifier metadata
    """
    class Meta:
        model = Project
        fields = ('project_home_page', 'license', 'data_use_agreement')

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
        self.inviter = inviter
        self.project = project

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
