from django.conf.urls import include
from django.contrib import admin
from django.urls import path
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

    path('lightwave/', include('lightwave.urls')),

    path('', views.home, name='home'),

    # about pages
    path('about/publish/', views.about_publish,
        name='about_publish'),
    path('about/', views.about, name='about'),
    path('about/faq/', views.faq, name='faq'),
    path('about/licenses/<license_slug>/', views.license_content,
        name='license_content'),
    path('about/citi-course/', views.citi_course, name='citi_course'),

    # robots.txt for crawlers
    path('robots.txt', lambda x: HttpResponse("User-Agent: *\nDisallow: /", content_type="text/plain"), name="robots_file"),
]
