from django import forms
from django.template.defaultfilters import slugify
import os

from .models import Project, StorageRequest
from .utility import readable_size
from physionet.settings import MEDIA_ROOT


class MultiFileFieldForm(forms.Form):
    """
    Form for uploading multiple files
    """
    file_field = forms.FileField(widget=forms.ClearableFileInput(attrs={'multiple': True}))

    def __init__(self, individual_size_limit, total_size_limit, taken_names, *args, **kwargs):
        # Email choices are those belonging to a user
        super(MultiFileFieldForm, self).__init__(*args, **kwargs)
        self.individual_size_limit = individual_size_limit
        self.total_size_limit = total_size_limit
        self.taken_names = taken_names

    def clean_file_field(self):
        """
        Check for file size limits and prevent upload when existing
        file/folder exists in directory
        """
        data = self.cleaned_data['file_field']

        files = self.files.getlist('file_field')
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
                    raise forms.ValidationError('Item named: "%(taken_name)s" already exists in current directory.',
                        code='taken_name', params={'taken_name':file.name})
            else:
                # Special error
                raise forms.ValidationError('Could not read the uploaded file')
        
        return data


class FolderCreationForm(forms.Form):
    """
    Form for specifying folder name
    """
    folder_name = forms.CharField(max_length=50)

    def __init__(self, taken_names, *args, **kwargs):
        # Email choices are those belonging to a user
        super(FolderCreationForm, self).__init__(*args, **kwargs)
        self.taken_names = taken_names

    def clean_folder_name(self,):
        """
        Prevent upload when existing file/folder exists in directory
        """
        data = self.cleaned_data['folder_name']
        if data in self.taken_names:
            raise forms.ValidationError('Item named: "%(taken_name)s" already exists in current directory.',
                code='taken_name', params={'taken_name':file.name})

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
