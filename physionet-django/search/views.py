from django.http import HttpResponse, Http404
from django.template import Context, Template
from django.template.loader import get_template
from django.db.models import Count
from physiobank.models import Database, DataType
from physionet.settings import PHYSIOBANK_ROOT
import os
import datetime



def findrecords():
    return

def recordsearch(request):
    # Retrieve and render the template
    template = get_template('search/recordsearch.html')

    context = Context({})

    html = template.render(context)
    return HttpResponse(html)



def dbsearch():
    return