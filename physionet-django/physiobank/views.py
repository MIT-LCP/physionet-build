from django.http import HttpResponse
from django.template import Context, Template
from django.template.loader import get_template
from .models import Database, DataType


# Physiobank home page
def home(request):
    
    # Retrieve and render the template
    template = get_template('physiobank/home.html')
    html = template.render()

    return HttpResponse(html)

# Database index page
def database_index(request):
    
    # The list of data types
    datatypes=DataType.objects.order_by('name')

    # Retrieve and render the template
    template = get_template('physiobank/database_index.html')
    context = Context({'datatypes': datatypes})
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