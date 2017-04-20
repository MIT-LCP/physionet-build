from django.http import HttpResponse, Http404
from django.template import Context, Template
from django.template.loader import get_template
from django.db.models import Count
from .models import Database, DataType
from physionet.settings import STATIC_ROOT
import os
from catalog.views import downloadfile

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

# Individual database page - returns the index with the list of files, or an individual file to download
def database(request, dbslug, sublink=''):
    # Get the database descriptors
    database = Database.objects.get(slug=dbslug)

    # Index page - show files and subdirectories in index
    if sublink=='':
        # Directory in which to search for files
        filedir = os.path.join(STATIC_ROOT, 'database', dbslug)
    else:
        # Test whether the sublink points to a file or directory
        filedir = os.path.join(STATIC_ROOT, 'database', dbslug, sublink)
        # Points to a valid directory
        if os.path.isdir(filedir):
            pass
        # Just return the single file to download
        elif os.path.isfile(filedir):
            return downloadfile(request, filedir)
        # No target
        else:
            raise Http404

    # The file names in the directory
    filenames = [f for f in os.listdir(filedir) if os.path.isfile(os.path.join(filedir, f)) and not f.endswith('~')]
    # The further subdirectories in the directory
    dirnames = [f for f in os.listdir(filedir) if not os.path.isfile(os.path.join(filedir, f)) and not f.endswith('~')]
    
    # Retrieve and render the template
    template = get_template('physiobank/database.html')

    context = Context({'database': database, 'filedir': filedir, 'filenames': filenames, 'dirnames': dirnames})

    html = template.render(context)

    return HttpResponse(html)

