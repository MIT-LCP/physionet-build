from django import forms
from ckeditor.fields import RichTextField
from physionetworks.models import Project
from physiobank.models import WFDB_Signal_Type


comparitors = (('EQ','=='), ('GTE','>='), ('LTE','<='), ('BTW','a<=X<=b'))



helpmsg = {
    'recordname':'Base name of WFDB record',
    'fs':'Base sampling frequency (Hz) of WFDB record',
    'duration':'DD HH:MM:SS.uuuuuu',
    'age':'Age in years (integer)',
    'gender':'Male or female',

    'signame':'Name of the signal'
}


# Fields for overall record
class RecordSearchForm(forms.Form):
    recordname = forms.CharField(label='Record Name', max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'name':'recordname'}))

    fs_0 = forms.FloatField(label='Fs', min_value=0.0001, required=False, widget=forms.TextInput(attrs={'class':'form-control', 'name':'fs_0'}))
    fs_1 = forms.FloatField(label='Fs', min_value=0.0001, required=False, widget=forms.TextInput(attrs={'class':'form-control', 'name':'fs_1'}))
    fs_comparitor = forms.ChoiceField(label='Fs Comparitor', choices=comparitors, required=False, widget=forms.Select(attrs={'class': 'form-control', 'name': 'fs_comparitor'}))

    duration_0 = forms.DurationField(label='Duration', required=False,widget=forms.TextInput(attrs={'class': 'form-control', 'name': 'duration_0'}))
    duration_1 = forms.DurationField(label='Duration', required=False,widget=forms.TextInput(attrs={'class': 'form-control', 'name': 'duration_1'}))
    duration_comparitor = forms.ChoiceField(label='Duration Comparitor', choices=comparitors, required=False, widget=forms.Select(attrs={'class':'form-control', 'name':'age'}))

    age_0 = forms.IntegerField(label='Age', min_value=0, required=False, widget=forms.NumberInput(attrs={'class':'form-control', 'name':'age'}))
    age_1 = forms.IntegerField(label='Age', min_value=0, required=False, widget=forms.NumberInput(attrs={'class':'form-control', 'name':'age'}))
    age_comparitor = forms.ChoiceField(label='Age Comparitor', choices=comparitors, required=False, widget=forms.Select(attrs={'class':'form-control', 'name':'age'}))

    gender = forms.ChoiceField(label='Gender', choices=(('Any','Any'),('M','M'),('F','F')), required=False, widget=forms.Select(attrs={'class':'form-control', 'name':'gender'}))


# Fields for records' individual signals
class SignalSearchForm(forms.Form):
    signame = forms.CharField(label='Signal Name', max_length=100, required=False, widget=forms.TextInput(attrs={'class':'form-control', 'name':'signame'}))

    # These go together
    sigtype = forms.ModelChoiceField(queryset=WFDB_Signal_Type.objects.all(), label='Signal Type')
    nsigtype_0 = forms.IntegerField(label='Signal Type Number', min_value=0, required=False, widget=forms.NumberInput(attrs={'class':'form-control', 'name':'age'}))
    nsigtype_1 = forms.IntegerField(label='Signal Type Number', min_value=1, required=False, widget=forms.NumberInput(attrs={'class':'form-control', 'name':'age'}))
    nsigtype_comparitor = forms.ChoiceField(label='Signal Type Number Comparitor', choices=comparitors, required=False, widget=forms.Select(attrs={'class':'form-control', 'name':'age'}))


    fs_0 = forms.FloatField(label='Fs', min_value=0.0001, required=False, widget=forms.TextInput(attrs={'class':'form-control', 'name':'fs_0', 'id':'fa-archive'}))
    fs_1 = forms.FloatField(label='Fs', min_value=0.0001, required=False, widget=forms.TextInput(attrs={'class':'form-control', 'name':'fs_1', 'id':'fa-archive'}))
    fs_comparitor = forms.ChoiceField(label='Fs Comparitor', choices=comparitors, required=False, widget=forms.Select(attrs={'class': 'form-control', 'name':'fs_comparitor'}))





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

    def clean(self):
        name = self.clean_name()
        super(CreateProjectForm, self).clean()

    def clean_name(self):
        if 'name' in self.cleaned_data:
            name = self.cleaned_data['name']
            return name


class ProjectTypeForm(forms.Form):
    projecttype = forms.ChoiceField(label='Project Type', choices=projecttypes, required=True, widget=forms.RadioSelect(attrs={'class': 'form-control', 'name': 'projecttype'}))


class ProjectLicenseForm(forms.Form):
    license = forms.ChoiceField(label='License', choices=licenses, initial={'N/A': 'N/A'}, required=True, widget=forms.Select(attrs={'class': 'form-control', 'name': 'license', 'id':'fa-certificate'}))
    access = forms.ChoiceField(label='Access Policy', choices=accesstypes, initial={'N/A': 'N/A'}, required=True, widget=forms.Select(attrs={'class': 'form-control', 'name': 'access', 'id':'fa-lock'}))


class FileFieldForm(forms.Form):
    file_field = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={'multiple': True}))

