from django.http import HttpResponse, Http404
from django.template.loader import get_template


def home(request):

    template = get_template('home.html')
    html = template.render()
    return HttpResponse(html)