from django.http import HttpResponse
from django.template import Context, Template
from django.template.loader import get_template
from .models import *
from .forms import CreateProjectForm

from IPython.display import display

# Physionetworks home page
def home(request):
    
    # Retrieve and render the template
    template = get_template('physionetworks/home.html')
    html = template.render()

    return HttpResponse(html)

# Create new project page
def create_project(request):


    display(CreateProjectForm.__dict__)
    print('im here')

    # Get the form
    form = CreateProjectForm()



    # Retrieve and render the template
    template = get_template('physionetworks/create-project.html')
    context = Context({'form': form})
    html = template.render(context)

    return HttpResponse(html)