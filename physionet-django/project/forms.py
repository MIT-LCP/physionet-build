from django import forms
from django.template.defaultfilters import slugify

from ckeditor.widgets import CKEditorWidget

from.models import Project, StorageRequest, metadata_models
import pdb

class ProjectCreationForm(forms.ModelForm):
    """
    For creating projects
    """
    title = forms.CharField(max_length=200)
    abstract = forms.CharField(widget=CKEditorWidget())

    class Meta:
        model = Project
        fields = ('resource_type',)

    def save(self, owner):
        project = super(ProjectCreationForm, self).save(commit=False)
        project.owner = owner
        
        # Save title and abstract in the metadata model
        metadata = metadata_models[self.cleaned_data['resource_type'].description].objects.create(
            title = self.cleaned_data['title'],
            slug = slugify(self.cleaned_data['title']),
            abstract = self.cleaned_data['abstract']
            )
        project.metadata = metadata
        project.save()
        project.collaborators.add(owner)
        return project


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
