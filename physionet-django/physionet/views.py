from django.template import loader, RequestContext
from django.contrib import messages
from django.http import HttpResponse, Http404

def home(request):
    c = RequestContext(request, {'user': request.user, 'messages': messages.get_messages(request)})
    return HttpResponse(loader.get_template('home.html').render(c))
