from django.conf.urls import url, include
from django.contrib import admin

from . import views

urlpatterns = [
    url(r'^admin/', admin.site.urls),

    url(r'^$', views.home, name='home'),

    # publish pages
    url(r'^author-guidelines/$', views.author_guidelines, name='author_guidelines'),

    # about pages
    url(r'^about-physionet/$', views.about_physionet, name='about_physionet'),
    url(r'^faq/$', views.faq, name='faq'),

    url(r'^our-team/$', views.our_team, name='our_team'),
    url(r'^funding/$', views.funding, name='funding'),

    # contact pages
    url(r'^contact/$', views.contact, name='contact'),

    # content pages
    url(r'^data/$', views.data, name='data'),
    url(r'^software/$', views.software, name='software'),
    url(r'^challenge/$', views.challenge, name='challenge'),

    # user account pages
    url(r'^', include('user.urls')),

    # project pages
    url(r'^projects/', include('project.urls')),
]

