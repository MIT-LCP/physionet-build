from django import forms
from django.template.defaultfilters import slugify
import os

from .models import Project, StorageRequest
from .utility import readable_size, list_items, list_directories
from physionet.settings import MEDIA_ROOT
import pdb


illegal_patterns = ['/','..',]


class MultiFileFieldForm(forms.Form):
    """
    Form for uploading multiple files
    """
    file_field = forms.FileField(widget=forms.ClearableFileInput(attrs={'multiple': True}))

    def __init__(self, individual_size_limit, total_size_limit, current_directory, *args, **kwargs):
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
        
        self.taken_names = list_items(self.current_directory, return_separate=False)

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
        validation_errors = []

        destination_folder = self.cleaned_data['destination_folder']
        selected_items = self.cleaned_data['selected_items']

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


class ProjectCreationForm(forms.ModelForm):
    """
    For creating projects
    """
    class Meta:
        model = Project
        fields = ('resource_type', 'title', 'abstract', 'owner', 'storage_allowance')
        widgets = {'owner': forms.HiddenInput(),
        'storage_allowance': forms.HiddenInput()}

    def save(self):
        project = super(ProjectCreationForm, self).save()
        owner = self.cleaned_data['owner']
        project.collaborators.add(owner)
        # Create file directory
        os.mkdir(project.file_root())
        return project


class DatabaseMetadataForm(forms.ModelForm):
    """
    Form for editing the metadata of a project with resource_type == database
    """
    class Meta:
        model = Project
        fields = ('title', 'abstract', 'background', 'methods',
            'data_description', 'acknowledgements', 'paper_citations',
            'references', 'topics', 'dua', 'training_course',
            'id_verification_required', 'version_number', 'changelog',)


class SoftwareMetadataForm(forms.ModelForm):
    """
    Form for editing the metadata of a project with resource_type == database
    """
    class Meta:
        model = Project
        fields = ('title', 'abstract', 'technical_validation', 'usage_notes',
            'source_controlled_location', 'acknowledgements', 'paper_citations',
            'references', 'topics', 'dua', 'training_course',
            'id_verification_required', 'version_number', 'changelog',)


# The modelform for editing metadata for each resource type
metadata_forms = {'Database':DatabaseMetadataForm, 'Software':SoftwareMetadataForm}


class CollaboratorChoiceForm(forms.Form):
    """
    For choosing project collaborators. Queryset is all project collaborators,
    optionally excluding the owner. Used for selecting new owner and removing
    collaborators.
    """
    collaborator = forms.ModelChoiceField(queryset=None, to_field_name='email',
        label='email', widget=forms.Select())

    def __init__(self, project, include_owner=False, *args, **kwargs):
        # Email choices are those belonging to a user
        super(CollaboratorChoiceForm, self).__init__(*args, **kwargs)

        collaborators = project.collaborators.all()

        if not include_owner:
            collaborators = collaborators.exclude(id=project.owner.id)

        self.fields['collaborator'].queryset = collaborators
        self.project = project


class CollaboratorInviteForm(forms.Form):
    """
    Form to invite new collaborators
    """
    collaborator = forms.EmailField()

    def __init__(self, project, *args, **kwargs):
        super(CollaboratorInviteForm, self).__init__(*args, **kwargs)
        self.project = project

    def clean_collaborator(self):
        "Ensure invite is sent to a non-collaborator"
        data = self.cleaned_data['collaborator']

        if data in [c.email for c in self.project.collaborators.all()]:
            raise forms.ValidationError('The user is already a collaborator of this project',
                code='already_collaborator')

        return data




class StorageRequestForm(forms.ModelForm):
    """
    Making a request for storage capacity for a project
    """
    # Storage request in GB
    request_allowance = forms.IntegerField(min_value=1, max_value=10000)

    class Meta:
        model = StorageRequest
        fields = ('request_allowance', 'project')
        widgets = {
            'request_allowance':forms.NumberInput(),
            'project':forms.HiddenInput()
        }

    def clean(self):
        """
        Storage size must be reasonable
        """
        # pdb.set_trace()
        current_allowance = self.cleaned_data['project'].storage_allowance
        request_allowance = self.cleaned_data['request_allowance']
        
        if request_allowance <= current_allowance:
            raise forms.ValidationError('Project already has the requested capacity.',
                code='already_has_allowance')


class StorageResponseForm(forms.Form):
    """
    Form for responding to a storage request
    """
    project_id = forms.IntegerField(widget= forms.HiddenInput())
    response = forms.ChoiceField(choices=[('Approve','Approve'), ('Reject','Reject')])
    message = forms.CharField(max_length=500, required=False, widget = forms.Textarea())


