from django.http import HttpResponse
from oauth2_provider.views.generic import ProtectedResourceView


class hello(ProtectedResourceView):
    def get(self, request, *args, **kwargs):
        return HttpResponse('Hello, OAuth2!')
