from django import forms
from ckeditor.fields import RichTextField



projecttypes = ((1, 'Data'),(2,'Software'),(3,'Tutorial'))
accesstypes = ((1, 'Open'),(2,'Protected'))
licenses = ((1,'GPL'),(2,'MIT'))



class CreateProjectForm(forms.Form):
    name = forms.CharField(label='Project Name', max_length=100, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'name': 'name', 'id':'fa-book'}))
    overview = forms.CharField(label='Overview', max_length=1500, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'name': 'overview', 'id':'fa-pencil'}))

    # This will be changed into a js object with autocomplete
    keywords = forms.CharField(label='Keywords', max_length=50, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'name': 'keywords', 'id':'fa-tags'}))
    contributors = forms.CharField(label='Contributors', max_length=50, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'name': 'contributors', 'id':'fa-users'}))
    contacts = forms.CharField(label='Contact', max_length=50, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'name': 'contacts', 'id':'fa-envelope'}))
    required_size = forms.FloatField(label='Required Space (GB)', min_value=1, required=True, widget=forms.NumberInput(attrs={'class': 'form-control', 'name': 'required_size', 'id':'fa-archive'}))


class ProjectTypeForm(forms.Form):
    projecttype = forms.ChoiceField(label='Project Type', choices=projecttypes, required=True, widget=forms.RadioSelect(attrs={'class': 'form-control', 'name': 'projecttype'}))


class ProjectLicenseForm(forms.Form):
    license = forms.ChoiceField(label='License', choices=licenses, initial={'N/A': 'N/A'}, required=True, widget=forms.Select(attrs={'class': 'form-control', 'name': 'license', 'id':'fa-certificate'}))
    access = forms.ChoiceField(label='Access Policy', choices=accesstypes, initial={'N/A': 'N/A'}, required=True, widget=forms.Select(attrs={'class': 'form-control', 'name': 'access', 'id':'fa-lock'}))


class FileFieldForm(forms.Form):
    file_field = forms.FileField(widget=forms.ClearableFileInput(attrs={'multiple': True}))

