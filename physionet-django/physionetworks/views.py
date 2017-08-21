from .forms import *
#CreateProjectForm, ProjectTypeForm, ProjectLicenseForm, ProjectContactForm, FileFieldForm, ProjectDatabaseForm, ProjectToolkitForm, ProjectMiscellaneousForm, LinkForm, BaseLinkFormSet, CollaboratorForm, BaseCollaboratorFormSet
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.template.loader import get_template
from django.template import Context, Template
from django.http import HttpResponse
from django.middleware import csrf
from catalog.models import File
from uuid import uuid4
from .models import Project

from IPython.display import display

from django.forms.formsets import formset_factory

# from physionetworks.forms import CreateProjectForm, ProjectTypeForm, ProjectLicenseForm, FileFieldForm, ProjectDatabaseForm, ProjectToolkitForm
# from physionetworks.models import Project

# Physionetworks home page
def home(request):
    # Retrieve and render the template
    template = get_template('physionetworks/home.html').render(Context({'home': True}))
    return HttpResponse(template)

# Create new project page
@login_required(login_url="/login/")#If the User is not logged in it will be redirected to the login URL.
def create_project(request):
    user = request.user
    LinkFormSet         = formset_factory(LinkForm, formset=BaseLinkFormSet)
    CollaboratorFormSet = formset_factory(CollaboratorForm, formset=BaseCollaboratorFormSet)

    if request.method == 'POST':#If we receive a post in the web request
        ContactForm  = ProjectContactForm(request.POST, prefix="Contact")
        CreateForm   = CreateProjectForm(request.POST, prefix="Create")
        TypeForm     = ProjectTypeForm(request.POST, prefix="Type")
        AccessForm   = ProjectLicenseForm(request.POST, prefix="Access")
        DatabaseForm = ProjectDatabaseForm(request.POST, prefix="Database")
        link_formset = LinkFormSet(request.POST, prefix="link_page")
        ToolkitForm  = ProjectToolkitForm(request.POST, prefix="Tool")
        MiscellaneousForm    = ProjectMiscellaneousForm(request.POST, prefix="Miscellaneous")
        Collaborator_FormSet = CollaboratorFormSet(request.POST, prefix="colab")
        try:
            if DatabaseForm.is_valid():
                filedescription = DatabaseForm.cleaned_data['filedescription']
                collection      = DatabaseForm.cleaned_data['collection']
                datatypes       = DatabaseForm.cleaned_data['datatypes']
                # datatypes TO BE DEFINED **************************************************************************************
            if ToolkitForm.is_valid():
                languages = ToolkitForm.cleaned_data['languages']
                installation = ToolkitForm.cleaned_data['installation']
                usage = ToolkitForm.cleaned_data['usage']
                testedplatforms = ToolkitForm.cleaned_data['testedplatforms']
                # testedplatforms TO BE DEFINED ********************************************************************************

            if link_formset.is_valid():
                for indx, link_form in enumerate(link_formset):
                    description = link_form.cleaned_data.get('description')
                    link        = link_form.cleaned_data.get('link')

            if Collaborator_FormSet.is_valid():
                for indx, colab in enumerate(Collaborator_FormSet):
                    Colaborator = colab.cleaned_data.get('collaborators')

            if MiscellaneousForm.is_valid():
                slug = MiscellaneousForm.cleaned_data.get('slug')
                acknowledgements = MiscellaneousForm.cleaned_data.get('acknowledgements')

# Create Contributor()
# Create contact

#WORK WITH Keywords comma separated.
# keywords - comma separated
# contributors - name, institution
# contacts - name, email, institution
# collaborators - email - users, comma separated
# databaseinfo, toolkitinfo
#     license = models.ForeignKey('catalog.License', default=None, related_name="%(app_label)s_%(class)s",)
#     keywords = models.ManyToManyField('catalog.Keyword', related_name="%(app_label)s_%(class)s", blank=True)
#     contributors = models.ManyToManyField('catalog.Contributor', related_name="%(app_label)s_%(class)s", blank=True)
#     contacts = models.ManyToManyField('catalog.Contact', related_name="%(app_label)s_%(class)s", blank=True)
#     associated_pages = models.ManyToManyField('catalog.Link', related_name="%(app_label)s_%(class)s", blank=True)



        #     if CreateForm.is_valid() and TypeForm.is_valid() and AccessForm.is_valid():

        #         New_Project = Project(owner=user, projecttype=TypeForm.cleaned_data['projecttype'],slug=slug
        #             requestedstorage=CreateForm.cleaned_data['required_size'], name=CreateForm.cleaned_data['name'], 
        #             license=License.objects.get(id=AccessForm.cleaned_data['license']), keywords=CreateForm.cleaned_data['keywords'], 
        #             overview=CreateForm.cleaned_data['overview'], contributors=CreateForm.cleaned_data['contributors'], 
        #             contacts=CreateForm.cleaned_data['contacts'], isopen=AccessForm.cleaned_data['access'], 
        #             acknowledgements=acknowledgements)
        #         New_Project.save()


                #
                # Create model
                #
                if request.FILES:
                    Files = request.FILES.getlist('File-file_field')
                    for item in Files:
                        uuid = uuid4()
                        result = None
                        while result is None:
                            try:
                                File.objects.get(id=uuid)
                                uuid = uuid4()
                            except:
                                result = True
                                #
                                # What is this form ID
                                #
                        File = File(Pid=form.id,name = item.name, size = item.size, file = item, extension = item.name.split('.')[-1])
                        File.save()
                        #
                        # Add file to many to many - associated_files
                        #
                else:
                    print "IGNORE -- NO FILES"
        except Exception as e:
            print e, "FORM NOT VALID"
            #
            # Create errror
            #

    if 'Collaborator_FormSet' not in locals(): Collaborator_FormSet = CollaboratorFormSet(prefix="colab")
    if 'link_formset'        not in locals(): link_formset = LinkFormSet(prefix="link_page")
    if 'CreateForm'          not in locals(): CreateForm   = CreateProjectForm(prefix="Create")
    if 'TypeForm'            not in locals(): TypeForm     = ProjectTypeForm(prefix="Type")
    if 'AccessForm'          not in locals(): AccessForm   = ProjectLicenseForm(prefix="Access")
    if 'DatabaseForm'        not in locals(): DatabaseForm = ProjectDatabaseForm(prefix="Database")
    if 'ToolkitForm'         not in locals(): ToolkitForm  = ProjectToolkitForm(prefix="Tool")
    if "ContactForm"         not in locals(): ContactForm  = ProjectContactForm(prefix="Contact")
    if 'MiscellaneousForm'   not in locals(): MiscellaneousForm = ProjectMiscellaneousForm(prefix="Miscellaneous")


    FileForm   = FileFieldForm(prefix="File")

    # Retrieve and render the template
    context = Context({'CreateForm':CreateForm, 'link_formset':link_formset, 'ContactForm':ContactForm, 'Collaborator_FormSet':Collaborator_FormSet, 'FileForm':FileForm, 'MiscellaneousForm':MiscellaneousForm, 'TypeForm':TypeForm, 'ToolkitForm':ToolkitForm, 'DatabaseForm':DatabaseForm, 'AccessForm':AccessForm, 'csrf_token': csrf.get_token(request), 'user':user})
    html = get_template('physionetworks/create-project.html').render(context)

    return HttpResponse(html)




