from django.forms import Form, CharField, FloatField, TextInput, URLField, URLInput, NumberInput, EmailInput, SlugField, ChoiceField, RadioSelect, Select, FileField, ClearableFileInput, CheckboxSelectMultiple, MultipleChoiceField
from catalog.models import ProjectDatabase, ProjectToolkit, License, Keyword
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from ckeditor.fields import RichTextFormField
from django.forms.formsets import BaseFormSet
from ckeditor.widgets import CKEditorWidget
from models import Project
from requests import get
from re import match
projecttypes = ((1, 'Data'),(2,'Software'),(3,'Tutorial'))
accesstypes = ((1, 'Open'),(2,'Protected'))
licenses = []
for item in License.objects.all():
    licenses.append((item.id, item))

# help_text="This is the grey text"
class CreateProjectForm(Form):
    name     = CharField(label='Project Name', max_length=100, required=True, widget=TextInput(attrs={'placeholder':'Project Name.', 'class': 'form-control', 'name': 'name', 'id':'fa-book'}))
    overview = CharField(label='Overview', max_length=1500, required=True, widget=TextInput(attrs={'placeholder':'Brief Project Overview.', 'class': 'form-control', 'name': 'overview', 'id':'fa-pencil'}))
    keywords = ChoiceField(label='Keywords', required=True, choices=Keyword.objects.all(), widget=TextInput(attrs={'placeholder':'Tag project with keywords', 'class': 'form-control', 'name': 'keywords', 'id':'fa-tags'}))
    contributors  = CharField(label='Contributors', max_length=50, required=True, widget=TextInput(attrs={'placeholder':'Contributors email.', 'class': 'form-control', 'name': 'contributors', 'id':'fa-users'}))
    required_size = FloatField(label='Required Space (GB)', min_value=1, required=True, widget=NumberInput(attrs={'placeholder':'Number in GB of required space.', 'class': 'form-control', 'name': 'required_size', 'id':'fa-archive'}))
    # -- keywords -- will be changed into a js object with autocomplete

    def clean(self):
        name = self.clean_name()
        super(CreateProjectForm, self).clean()

    def clean_name(self):
        if 'name' in self.cleaned_data:
            name = self.cleaned_data['name']
            return name

class ProjectContactForm(Form):
    name = CharField(label='Contact', max_length=100, required=True, widget=TextInput(attrs={'placeholder':'Contact Full Name', 'class': 'form-control', 'name': 'contact', 'id':'fa-envelope'}))
    email = CharField(label='Email', max_length=50, required=True, widget=TextInput(attrs={'placeholder':'Contact Email', 'class': 'form-control', 'name': 'email', 'id':'fa-envelope'}))
    institution = CharField(label='Institution', max_length=100, required=True, widget=TextInput(attrs={'placeholder':'Contact Institution', 'class': 'form-control', 'name': 'institution', 'id':'fa-envelope'}))

class ProjectMiscellaneousForm(Form):
    slug = SlugField(label='Slug', required=False, widget=TextInput(attrs={'class': 'form-control', 'name': 'slug'}))
    acknowledgements = RichTextFormField(label='Acknowledgements', widget=CKEditorWidget(attrs={'class': 'form-control', 'name': 'acknowledgements', 'style':'width: 100%;'}))

class ProjectTypeForm(Form):
    projecttype = ChoiceField(label='Project Type', choices=projecttypes, required=True, widget=RadioSelect(attrs={'class': 'form-control', 'name': 'projecttype', 'style':'box-shadow:none'}))


class ProjectLicenseForm(Form):
    license = ChoiceField(label='License', choices=tuple(licenses), initial={'N/A': 'N/A'}, required=True, widget=Select(attrs={'class': 'form-control', 'name': 'license', 'id':'fa-certificate'}))
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
        fields  = ['collection', 'filedescription', 'datatypes']

class ProjectToolkitForm(Form):
    installation    = RichTextFormField(label='Installation', widget=CKEditorWidget(attrs={'class': 'form-control', 'name': 'installation'}))
    usage           = RichTextFormField(label='Usage', widget=CKEditorWidget(attrs={'class': 'form-control', 'name': 'usage'}))
    testedplatforms = RichTextFormField(label='Tested Platforms', widget=CKEditorWidget(attrs={'class': 'form-control', 'name': 'testedplatforms'}))
    datatypes       = MultipleChoiceField(label='Data Type',  choices=projecttypes, widget=CheckboxSelectMultiple(attrs={'class': 'form-control', 'name': 'access', 'style':'box-shadow:none;text-align:center;float:none;'}))

    class Meta:
        model = ProjectDatabase
        fields  = ['installation', 'filedescription', 'datatypes']

# This form will be used in a form set, so that it can be duplicated as many times as the user wants.
# Also this form will a custom BaseForm set to overwrite the clean function ammong other things
class LinkForm(Form):
    description = CharField(label='Link Description', max_length=100, required=False, widget=TextInput(attrs={'class': 'form-control', 'placeholder': 'Link Description'}))#, 'name': 'link_description'}))
    link = URLField(label='Associated Pages', max_length=100, required=False, widget=URLInput(attrs={'placeholder': 'URL', 'class': 'form-control'}))#, 'name': 'link'}))

# This form will be used in a form set, so that it can be duplicated as many times as the user wants.
# Also this form will a custom BaseForm set to overwrite the clean function ammong other things
class CollaboratorForm(Form):
    collaborators = CharField(label='Collaborators', max_length=50, required=False, widget=EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email of the colaborator'}))

class BaseCollaboratorFormSet(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return

        colab = []
        duplicates = False
        for form in self.forms:
            if form.cleaned_data:
                collaborators = form.cleaned_data['collaborators']

                if collaborators in colab:
                    duplicates = True
                colab.append(collaborators)
                
                if duplicates:
                    raise ValidationError('There cannot be duplicates in the collaborators',code='Duplicate_Colab')

                if not match(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', collaborators):
                    raise ValidationError('There is a invalid email.',code='Invalid_Email')

class BaseLinkFormSet(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return

        descriptions = []
        urls = []
        duplicates = False
        for form in self.forms:
            if form.cleaned_data:
                description = form.cleaned_data['description']
                link = form.cleaned_data['link']
                if get(link).status_code >= 400:
                    raise ValidationError('There was a problem with the link',code='Bad_URL_Response')

                if description and link:
                    if description in descriptions:
                        duplicates = True
                    descriptions.append(description)

                    if link in urls:
                        duplicates = True
                    urls.append(link)

                if duplicates:
                    raise ValidationError('Links must have unique descriptions and URLs.',code='Duplicate_Links')
                # Check that all links have both an description and link
                if link and not description:
                    raise ValidationError('All links must have an description.',code='Missing_Description')
                elif description and not link:
                    raise ValidationError('All descriptions must have a URL.',code='Missing_Link')


# class ProjectToolkitForm(Form):
#     # Programming languages used
#     languages = models.ManyToManyField('physiotoolkit.Language', related_name="%(app_label)s_%(class)s")
