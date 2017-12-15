from django import forms
from django.template.defaultfilters import slugify
import os

from .models import Project, StorageRequest
from physionet.settings import MEDIA_ROOT


class FileFieldForm(forms.Form):
    file_field = forms.FileField(widget=forms.ClearableFileInput(attrs={'multiple': True}))


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
