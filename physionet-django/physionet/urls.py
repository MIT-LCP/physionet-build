"""physionet URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf import settings                                                
from django.conf.urls import include, url                                             
from django.conf.urls.static import static                                      
from django.contrib import admin
from users.views import login, logout, register, reset_password, activate
from search.views import recordsearch, dbsearch
from cwave.views import cwave


from . import views             
                                                                                
urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^$', views.home),

    # Users
    url(r'^home/', include('users.urls')),
    url(r'^logout/$', logout, name='logout'),
    url(r'^login/$', login, name='login'),
    url(r'^register/$', register, name='register'),
    url(r'^reset_password/[0-9a-z-]+/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', reset_password, name='reset_password'),
    url(r'^activate/[0-9a-z-]+/[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', activate, name='activate'),

    #Physionetworks
    url(r'^physioworks/', include('physionetworks.urls')),
    url(r'^physiobank/', include('physiobank.urls')),
    url(r'^physiotools/', include('physiotoolkit.urls')),

    # Search
    url(r'^recordsearch/', recordsearch),
    url(r'^dbsearch', dbsearch),

    # Wave View
    url(r'^cwave', cwave),



]+static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)+static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)



"""
Site-wide URLs:

physionet.org
physionet.org/database
physionet.org/recordsearch
physionet.org/dbsearch
physionet.org/cwave
physionet.org/works
physionet.org/software
physionet.org/challenge
physionet.org/home
physionet.org/about
physionet.org/news
physionet.org/faq
physionet.org/forum
"""