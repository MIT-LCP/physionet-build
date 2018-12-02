from django.conf.urls import url, include
from django.contrib import admin

from . import views
import project.views as project_views


urlpatterns = [
    # django admin app
    url(r'^admin/', admin.site.urls),
    # management console app
    url(r'^console/', include('console.urls')),
    # user app
    url(r'^', include('user.urls')),
    # project app
    url(r'^projects/', include('project.urls')),
    # notification app
    url(r'^', include('notification.urls')),

    url(r'^$', views.home, name='home'),
    # about pages
    url(r'^about/author-guidelines/$', views.author_guidelines,
        name='author_guidelines'),
    url(r'^about/physionet/$', views.about_physionet, name='about_physionet'),
    url(r'^about/development/$', views.development, name='development'),
    url(r'^about/faq/$', views.faq, name='faq'),
    url(r'^about/licenses/$', views.licenses, name='licenses'),
    url(r'^about/licenses/(?P<license_slug>[\w-]+)/$', views.license_content,
        name='license_content'),
    url(r'^about/duas/$', views.duas, name='duas'),
    url(r'^about/duas/(?P<dua_slug>[\w-]+)/$', views.dua_content,
        name='dua_content'),
    url(r'^about/contact/$', views.contact, name='contact'),
    url(r'^about/citi-instructions/$', views.citi_instructions, name='citi_instructions'),

    # content pages
    url(r'^data/$', views.data, name='data'),
    url(r'^software/$', views.software, name='software'),
    url(r'^content/$', views.content, name='content'),

    # published projects
    url(r'^content/(?P<published_project_slug>\w+)/$',
        project_views.published_project, name='published_project'),
    url(r'^content/(?P<published_project_slug>\w+)/files-panel/$',
        project_views.published_files_panel, name='published_files_panel'),
    url(r'^content/(?P<published_project_slug>\w+)/files/(?P<full_file_name>.+)$',
        project_views.serve_published_project_file, name='serve_published_project_file'),

    url(r'^sign-dua/(?P<published_project_slug>\w+)/$', project_views.sign_dua,
        name='sign_dua'),
]
