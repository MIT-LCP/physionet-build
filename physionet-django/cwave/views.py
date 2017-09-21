from django.http import HttpResponse, Http404
from django.template import Context, Template
from django.template.loader import get_template
from django.db.models import Count
from physiobank.models import Database, DataType
from physionet.settings import PHYSIOBANK_ROOT
import os
import datetime
from catalog.views import downloadfile
from catalog.models import File
from catalog.utility import get_display_file, get_display_directory




def cwave(request):
    template = get_template('cwave/cwave.html')
    html = template.render()

    return HttpResponse(html)

# Physiobank home page
def home(request):
    
    template = get_template('physiobank/home.html')
    html = template.render()

    return HttpResponse(html)

# Database index page
def database_index(request):
    
    # The list of data types
    datatypes=DataType.objects.order_by('name')

    # The list of databases (add filter() to change type into queryset instead of manager.Manager)
    databases=Database.objects.filter()

    # Databases ordered by date/popularity/name 
    date_dbs = {}
    pop_dbs = {}
    name_dbs = {}
    # For each data type
    for dt in datatypes:
        dt = dt.name

        # all the databases with certain data type (the DataType foreign key has name == ...)
        dbtype = databases.filter(datatypes__name=dt)
        date_dbs[dt] = dbtype.order_by('-publishdate')
        pop_dbs[dt] = dbtype.order_by('visits')
        name_dbs[dt] = dbtype.order_by('name')

    # For multicategory databases. Do >1
    dbmulti = databases.annotate(num_datatypes=Count('datatypes')).filter(num_datatypes=2)
    date_dbs['multi'] = dbmulti.order_by('-publishdate')
    pop_dbs['multi'] = dbmulti.order_by('visits')
    name_dbs['multi'] = dbmulti.order_by('name')

    # Retrieve and render the template
    template = get_template('physiobank/database_index.html')

    context = Context({'datatypes': datatypes, 'date_dbs': date_dbs,
                       'pop_dbs': pop_dbs, 'name_dbs': name_dbs, 'multi':'multi'})

    html = template.render(context)

    return HttpResponse(html)

# Individual database page: index, subdirectory, or individual file to download
def database(request, dbslug, sublink=''):
    
    db = Database.objects.get(slug=dbslug)

    # Index page
    if sublink=='':
        # Directory in which to search for files
        filedir = os.path.join(PHYSIOBANK_ROOT, dbslug)
        insubdir = False
    else:
        # Test whether the sublink points to a file or directory
        filedir = os.path.join(PHYSIOBANK_ROOT, dbslug, sublink)
        # Points to a valid directory
        if os.path.isdir(filedir):
            insubdir=True
        # Just return the single file to download
        elif os.path.isfile(filedir):
            return downloadfile(request, filedir)
        # No target
        else:
            raise Http404

    # Show subdirectories if any.
    # Show files if any: name, last modified, size, description (based on extension) 

    filenames = sorted([f for f in os.listdir(filedir) if os.path.isfile(os.path.join(filedir, f)) and not f.endswith('~')])
    dirnames = sorted([d for d in os.listdir(filedir) if os.path.isdir(os.path.join(filedir, d))])
    
    if filenames != []:
        displayfiles = [get_display_file(os.path.join(filedir, f)) for f in filenames]
    else:
        displayfiles = []
    if dirnames != []:
        displaydirs = [get_display_directory(os.path.join(filedir, d)) for d in dirnames]
    else:
        displaydirs = []

    print(db.license.url)

    # Retrieve and render the template
    template = get_template('physiobank/database.html')
    context = Context({'database': db, 'insubdir': insubdir, 'displayfiles': displayfiles, 'displaydirs': displaydirs})
    html = template.render(context)

    return HttpResponse(html)

