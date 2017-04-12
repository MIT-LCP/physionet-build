from django.http import HttpResponse
from django.template import loader, RequestContext

# Physionet home Page
def home(request):
    return HttpResponse(loader.get_template('home.html').render(RequestContext(request, {'user': request.user})))
