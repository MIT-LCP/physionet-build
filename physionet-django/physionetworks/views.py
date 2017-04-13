from django.http import HttpResponse
from django.template import Context, Template
from django.template.loader import get_template
from .models import *
from .forms import CreateProjectForm, ProjectTypeForm, ProjectLicenseForm, FileFieldForm

from IPython.display import display

# Physionetworks home page
def home(request):
    
    # Retrieve and render the template
    template = get_template('physionetworks/home.html').render(Context({'home': True}))

    return HttpResponse(template)

# Create new project page
def create_project(request):
    
    # Retrieve and render the template
    context = Context({'form': CreateProjectForm(), 'FileForm' :FileFieldForm(),  'typeform': ProjectTypeForm(), 'accessform':ProjectLicenseForm(), 'create': True})
    html = get_template('physionetworks/create-project.html').render(context)

    return HttpResponse(html)