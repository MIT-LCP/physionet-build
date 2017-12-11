from django import forms
from django.template.defaultfilters import slugify

from ckeditor.widgets import CKEditorWidget

from.models import Project, StorageRequest, metadata_models
import pdb

class ProjectCreationForm(forms.ModelForm):
    """
    For creating projects
    """
    abstract = forms.CharField(widget=CKEditorWidget())

    class Meta:
        model = Project
        fields = ('title', 'resource_type',)

    def save(self, owner):
        project = super(ProjectCreationForm, self).save(commit=False)
        project.owner=owner
        # Save title and abstract in the metadata model
        metadata = metadata_models[self.cleaned_data['resource_type'].description].objects.create(
            title = self.cleaned_data['title'],
            slug = slugify(self.cleaned_data['title']),
            abstract = self.cleaned_data['abstract']
            )
        project.metadata = metadata
        project.save()
        return project


# class ProjectForm(forms.ModelForm):
#     """
#     For editing projects
#     """
#     class Meta:
#         model = Project
#         fields = ('title', 'dua', 'training_course', 'id_verification_required',
#             'topics', 'abstract','background','methods','data_description',
#             'technical_validation','usage_notes','acknowledgements',
#             'paper_citations','references', 'owner','collaborators')

#         widgets = {
#             'first_name':forms.TextInput(attrs={'class':'form-control'}),
#             'middle_names':forms.TextInput(attrs={'class':'form-control'}),
#             'last_name':forms.TextInput(attrs={'class':'form-control'}),
#             'url':forms.TextInput(attrs={'class':'form-control'}),
#             'phone':forms.TextInput(attrs={'class':'form-control'}),
#         }


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



