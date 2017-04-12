from django import forms
from ckeditor.fields import RichTextField



projecttypes = ((1, 'Data'),(2,'Software'),(3,'Tutorial'))
accesstypes = ((1, 'Open'),(2,'Protected'))
licenses = ((1,'GPL'),(2,'MIT'))



class CreateProjectForm(forms.Form):
    name = forms.CharField(label='Project Name', max_length=100)
    projecttype = forms.ChoiceField(label='Project Type', choices=projecttypes)
    overview = forms.CharField(label='Overview', max_length=1500)

    # This will be changed into a js object with autocomplete
    license = forms.ChoiceField(label='License', choices=licenses)
    access = forms.ChoiceField(label='Access Policy', choices=accesstypes)
    keywords = forms.CharField(label='Keywords', max_length=50)

    contributors = forms.CharField(label='Contributors', max_length=50)
    contacts = forms.CharField(label='Contact', max_length=50)

    required_size = forms.FloatField(label='Required Space (GB)', min_value=1)
    