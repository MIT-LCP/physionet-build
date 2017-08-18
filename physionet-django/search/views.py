from django.http import HttpResponse, Http404
from django.template import Context, Template
from django.template.loader import get_template
from django.db.models import Count
from physiobank.models import Database, DataType
from .forms import RecordSearchForm, SignalSearchForm, helpmsg
from physionet.settings import PHYSIOBANK_ROOT
import os
import datetime






def findrecords():
    return

def recordsearch(request):


    recform = RecordSearchForm()
    sigform = SignalSearchForm()

    template = get_template('search/recordsearch.html')

    context = Context({'recform':recform, 'sigform':sigform,'helpmsg':helpmsg})

    html = template.render(context)
    return HttpResponse(html)


# Idea: Text file results. Export to lightwave.




def dbsearch():
    return