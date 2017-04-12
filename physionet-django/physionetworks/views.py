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




def get_name(request):
    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = NameForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            # process the data in form.cleaned_data as required
            # ...
            # redirect to a new URL:
            return HttpResponseRedirect('/thanks/')

    # if a GET (or any other method) we'll create a blank form
    else:
        form = NameForm()

    return render(request, 'name.html', {'form': form})