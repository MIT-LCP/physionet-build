from django.http import HttpResponse
from django.template import Context, Template
from django.template.loader import get_template
from django.db.models import Count
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

# Individual database page
def database(request, dbslug):
    # Get the database descriptors
    database = Database.objects.get(slug=dbslug)

    # Retrieve and render the template
    template = get_template('physiobank/database.html')

    context = Context({'database': database})

    html = template.render(context)

    return HttpResponse(html)