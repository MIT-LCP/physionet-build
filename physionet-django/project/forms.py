from django import forms
from django.template.defaultfilters import slugify
import os

from .models import Project, StorageRequest
from .utility import readable_size, list_items, list_directories
from physionet.settings import MEDIA_ROOT


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

        return data


class MoveItemsForm(forms.Form):
    """
    Form for moving items into a target folder
    The target_folder field is created upon form initialization, giving choices
    of current subdirectories.
    """
    def __init__(self, current_directory, in_subdir, selected_items=None, *args, **kwargs):
        super(MoveItemsForm, self).__init__(*args, **kwargs)
        self.current_directory = current_directory
        self.in_subdir = in_subdir
        self.selected_items = selected_items

        existing_subfolders = list_directories(self.current_directory)

        target_folder_choices = [(s, s) for s in existing_subfolders]
        if in_subdir:
            target_folder_choices = [('../', '*Parent Directory*')] + target_folder_choices

        self.fields['target_folder'] = forms.ChoiceField(
            choices=target_folder_choices, required=False
        )
        
    def clean_target_folder(self):
        """
        Target folder must exist, and must not contain items with the same name
        as the items to be moved.
        """
        data = self.cleaned_data['target_folder']

        # The directory contents might have changed between the the time the page was
        # loaded and when the user submits the form. Recheck directory contents.
        # TODO

        # Check the target directory for clashing names
        taken_names = list_items(os.path.join(self.current_directory, data), return_separate=False)
        clashing_names = set(self.selected_items).intersection(set(taken_names))

        if clashing_names:
            raise forms.ValidationError('Item named: "%(clashing_name)s" already exists in target folder.',
                code='clashing_name', params={'clashing_name':list(clashing_names)[0]})

        return data


class RenameItemForm(forms.Form):
    """
    Form for renaming an item in a directory
    """
    item_name = forms.CharField(max_length=50, required=False)

    def __init__(self, current_directory=None, selected_items=None, *args, **kwargs):
        super(RenameItemForm, self).__init__(*args, **kwargs)
        self.current_directory = current_directory
        self.selected_items = selected_items

    def clean_item_name(self):
        """
        Prevent rename when existing file/folder exists in directory.
        Prevent selection of multiple items
        """
        data = self.cleaned_data['item_name']
        self.taken_names = list_items(self.current_directory, return_separate=False)

        if len(self.selected_items) != 1:
            raise forms.ValidationError('Only one item may be renamed at a time.')

        if data in self.taken_names:
            raise forms.ValidationError('Item named: "%(taken_name)s" already exists in current folder.',
                code='clashing_name', params={'taken_name':data})

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


class StorageRequestForm(forms.ModelForm):
    """
    Making a request for storage capacity for a project
    """
    # Storage request in GB
    storage_size = forms.IntegerField(min_value=0, max_value=10000)

    class Meta:
        model = StorageRequest
        fields = ('storage_size',)
        widgets = {
            'storage_size':forms.NumberInput(attrs={'class':'form-control'})
        }
