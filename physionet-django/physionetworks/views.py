from .forms import CreateProjectForm, ProjectTypeForm, ProjectLicenseForm, FileFieldForm
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

# Physionetworks home page
def home(request):
    
    # Retrieve and render the template
    template = get_template('physionetworks/home.html').render(Context({'home': True}))

    return HttpResponse(template)

# Create new project page
@login_required(login_url="/login/")#If the User is not logged in it will be redirected to the login URL.
def create_project(request):
    user = request.user
    if request.method == 'POST':#If we receive a post in the web request
        CreateForm = CreateProjectForm(request.POST, prefix="Create")
        TypeForm   = ProjectTypeForm(request.POST, prefix="Type")
        AccessForm = ProjectLicenseForm(request.POST, prefix="Access")
        try:
            if CreateForm.is_valid() and TypeForm.is_valid() and AccessForm.is_valid():

                New_Project = Project(owner=user, projecttype=TypeForm.cleaned_data['projecttype'],storage=1,
                    requestedstorage=CreateForm.cleaned_data['required_size'], name=CreateForm.cleaned_data['name'], 
                    license=AccessForm.cleaned_data['license'], keywords=CreateForm.cleaned_data['keywords'], 
                    overview=CreateForm.cleaned_data['overview'], contributors=CreateForm.cleaned_data['contributors'], 
                    contacts=CreateForm.cleaned_data['contacts'], projectaccess=AccessForm.cleaned_data['access'])
                New_Project.save()

    
    # slug = models.SlugField(max_length=50, unique=True)
    # publishdate = models.DateField(blank=True)
    # associated_pages = models.ManyToManyField('catalog.Link', related_name="%(app_label)s_%(class)s", blank=True)
    # acknowledgements = models.TextField(blank=True)
    # associated_files = models.ManyToManyField('catalog.File', related_name="%(app_label)s_%(class)s", blank=True)

    # collaborators = models.ManyToManyField(User, related_name='project_collaborator', blank=True)
    # databaseinfo = models.OneToOneField(ProjectDatabase, default='', blank=True, null=True)
    # toolkitinfo = models.OneToOneField(Pr

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
    try:
        CreateForm
    except:
        CreateForm = CreateProjectForm(prefix="Create")
    try:
        TypeForm
    except:
        TypeForm   = ProjectTypeForm(prefix="Type")
    try:
        AccessForm
    except:
        AccessForm = ProjectLicenseForm(prefix="Access")
    FileForm   = FileFieldForm(prefix="File")

    # Retrieve and render the template
    context = Context({'CreateForm':CreateForm, 'FileForm':FileForm, 'TypeForm':TypeForm, 'AccessForm':AccessForm, 'csrf_token': csrf.get_token(request), 'user':user})
    html = get_template('physionetworks/create-project.html').render(context)

    return HttpResponse(html)




