from django.conf.urls import include, url
from django.contrib import admin
from django.urls import path, re_path
from django.http import HttpResponse

from . import views
import project.views as project_views

urlpatterns = [
    # django admin app
    path('admin/', admin.site.urls),
    # management console app
    path('console/', include('console.urls')),
    # user app
    path('', include('user.urls')),
    # project app
    path('projects/', include('project.urls')),
    # notification app
    path('', include('notification.urls')),
    # search app
    path('', include('search.urls')),
    # export app
    path('', include('export.urls')),

    path('', views.home, name='home'),
    # about pages
    path('about/author-guidelines/', views.author_guidelines,
        name='author_guidelines'),
    path('about/physionet/', views.about_physionet, name='about_physionet'),
    path('about/faq/', views.faq, name='faq'),
    path('about/licenses/', views.licenses, name='licenses'),
    path('about/licenses/<license_slug>/', views.license_content,
        name='license_content'),
    path('about/contact/', views.contact, name='contact'),
    path('about/citi-instructions/', views.citi_instructions, name='citi_instructions'),

    # content pages
    path('data/', views.data, name='data'),
    path('software/', views.software, name='software'),
    path('content/', views.content, name='content'),

    # published projects
    path('content/<published_project_slug>/',
        project_views.published_project, name='published_project'),
    path('content/<published_project_slug>/files-panel/',
        project_views.published_files_panel, name='published_files_panel'),
    re_path('content/(?P<published_project_slug>\w+)/get-file/(?P<full_file_name>.+)',
        project_views.serve_published_project_file, name='serve_published_project_file'),
    path('content/<published_project_slug>/view-license/',
        project_views.published_project_license, name='published_project_license'),
    path('content/<project_slug>/info/', project_views.project_info.as_view(), name='info'),

    url(r'^robots.txt', lambda x: HttpResponse("User-Agent: *\nDisallow: /", content_type="text/plain"), name="robots_file"),
]
