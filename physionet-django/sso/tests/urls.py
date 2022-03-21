from physionet.urls import urlpatterns as root_urlpatterns
from sso.urls import urlpatterns as sso_urlpatterns

urlpatterns = root_urlpatterns + sso_urlpatterns
