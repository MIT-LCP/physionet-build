from django.http import HttpResponse
from django.template.loader import get_template

# Physionet home Page
def home(request):
    template = get_template('home.html')
    html = template.render()
    return HttpResponse(html)
