from django.http import HttpResponse
from django.template import Context, Template
from django.template.loader import get_template
from .models import *


# Physiobank home page
def home(request):
    
    # Retrieve and render the template
    template = get_template('physiobank/home.html')
    html = template.render()

    return HttpResponse(html)

# Database index page
def database_index(request):
    
    # Get the list of databses
    dblist=Database.objects.order_by('-posted')

    # Retrieve and render the template
    template = get_template('physiobank/database_index.html')
    context = Context({'dblist': dblist})
    html = template.render(context)

    return HttpResponse(html)

# Individual database page
def database(request, dbslug):
    
    # Get the database descriptors


    # Retrieve and render the template
    template = get_template('physiobank/home.html')
    #context = Context({'bloglist': bloglist})
    html = template.render()

    return HttpResponse(html)