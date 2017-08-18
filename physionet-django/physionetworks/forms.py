from django.forms import Form, CharField, FloatField, TextInput, NumberInput, ChoiceField, RadioSelect, Select, FileField, ClearableFileInput, CheckboxSelectMultiple, MultipleChoiceField
# from ckeditor.fields import RichTextField
from ckeditor.widgets import CKEditorWidget
from ckeditor.fields import RichTextFormField

from models import Project
from catalog.models import ProjectDatabase, ProjectToolkit

projecttypes = ((1, 'Data'),(2,'Software'),(3,'Tutorial'))
accesstypes = ((1, 'Open'),(2,'Protected'))
licenses = ((1,'GPL'),(2,'MIT'))



class CreateProjectForm(Form):
    name = CharField(label='Project Name', max_length=100, required=True, widget=TextInput(attrs={'class': 'form-control', 'name': 'name', 'id':'fa-book'}))
    overview = CharField(label='Overview', max_length=1500, required=True, widget=TextInput(attrs={'class': 'form-control', 'name': 'overview', 'id':'fa-pencil'}))
    # This will be changed into a js object with autocomplete
    keywords = CharField(label='Keywords', max_length=50, required=True, widget=TextInput(attrs={'class': 'form-control', 'name': 'keywords', 'id':'fa-tags'}))
    contributors = CharField(label='Contributors', max_length=50, required=True, widget=TextInput(attrs={'class': 'form-control', 'name': 'contributors', 'id':'fa-users'}))
    contacts = CharField(label='Contact', max_length=50, required=True, widget=TextInput(attrs={'class': 'form-control', 'name': 'contacts', 'id':'fa-envelope'}))
    required_size = FloatField(label='Required Space (GB)', min_value=1, required=True, widget=NumberInput(attrs={'class': 'form-control', 'name': 'required_size', 'id':'fa-archive'}))

    def clean(self):
        name = self.clean_name()
        super(CreateProjectForm, self).clean()

    def clean_name(self):
        if 'name' in self.cleaned_data:
            name = self.cleaned_data['name']
            return name


class ProjectTypeForm(Form):
    projecttype = ChoiceField(label='Project Type', choices=projecttypes, required=True, widget=RadioSelect(attrs={'class': 'form-control', 'name': 'projecttype', 'style':'box-shadow:none'}))


class ProjectLicenseForm(Form):
    license = ChoiceField(label='License', choices=licenses, initial={'N/A': 'N/A'}, required=True, widget=Select(attrs={'class': 'form-control', 'name': 'license', 'id':'fa-certificate'}))
    access = ChoiceField(label='Access Policy', choices=accesstypes, initial={'N/A': 'N/A'}, required=True, widget=Select(attrs={'class': 'form-control', 'name': 'access', 'id':'fa-lock'}))


class FileFieldForm(Form):
    file_field = FileField(required=False, widget=ClearableFileInput(attrs={'multiple': True}))

#####
class ProjectDatabaseForm(Form):
    collection      = RichTextFormField(label='Collection', widget=CKEditorWidget(attrs={'class': 'form-control', 'name': 'collection', 'style':'width: 100%;'}))
    filedescription = RichTextFormField(label='Description', widget=CKEditorWidget(attrs={'class': 'form-control', 'name': 'description', 'style':'width: 100%;'}))
    datatypes       = MultipleChoiceField(label='Data Type',  choices=projecttypes, widget=CheckboxSelectMultiple(attrs={'class': 'form-control', 'name': 'access', 'style':'box-shadow:none;text-align:center;float:none;'}))

    class Meta:
        model = ProjectDatabase
        fields  = ['collection', 'filedescription', 'datatypes']#, 'last_name', 'email', 'organization', 'department', 'city', 'state', 'country', 'url', 'photo']

class ProjectToolkitForm(Form):
    installation    = RichTextFormField(label='Installation', widget=CKEditorWidget(attrs={'class': 'form-control', 'name': 'installation'}))
    usage           = RichTextFormField(label='Usage', widget=CKEditorWidget(attrs={'class': 'form-control', 'name': 'usage'}))
    testedplatforms = RichTextFormField(label='Tested Platforms', widget=CKEditorWidget(attrs={'class': 'form-control', 'name': 'testedplatforms'}))
    datatypes       = MultipleChoiceField(label='Data Type',  choices=projecttypes, widget=CheckboxSelectMultiple(attrs={'class': 'form-control', 'name': 'access', 'style':'box-shadow:none;text-align:center;float:none;'}))

    class Meta:
        model = ProjectDatabase
        fields  = ['installation', 'filedescription', 'datatypes']#, 'last_name', 'email', 'organization', 'department', 'city', 'state', 'country', 'url', 'photo']


# class ProjectToolkitForm(forms.Form):
#     # Programming languages used
#     languages = models.ManyToManyField('physiotoolkit.Language', related_name="%(app_label)s_%(class)s")
