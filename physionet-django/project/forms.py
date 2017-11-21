from django import forms

from ckeditor.fields import RichTextField

from.models import Project, StorageRequest


class ProjectCreationForm(forms.ModelForm):
    """
    For creating projects
    """
    title = forms.CharField(max_length=80)
    abstract = forms.CharField(max_length=10000)

    class Meta:
        model = Project
        fields = ('resource_type',)

    def save(self):
        # This should trigger the metadata object creation
        project = super(ProjectCreationForm, self).save()
        # Save title and abstract in metadata model
        project.metadata.title = self.cleaned_data.get('title')
        project.metadata.abstract = self.cleaned_data.get('abstract')
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



