import shutil

import lightwave.views as lightwave_views
import project.views as project_views
from django.conf import settings
from django.conf.urls import handler404, handler500, include
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
from physionet import views
from physionet.settings.base import StorageTypes

from export.views import database_list

handler403 = 'physionet.views.error_403'
handler404 = 'physionet.views.error_404'
handler500 = 'physionet.views.error_500'


urlpatterns = [
    # django admin app
    path('admin/', admin.site.urls),
    # management console app
    path('console/', include('console.urls')),
    # user app
    path('', include('user.urls')),
    # project app
    path('projects/', include('project.urls')),
    # events
    path('events/', include('events.urls')),
    # notification app
    path('', include('notification.urls')),
    # search app
    path('', include('search.urls')),
    # export app
    path('api/', include('export.urls')),
    # oauth app
    path('oauth/', include('oauth.urls')),

    path('', views.home, name='home'),
    path('ping/', views.ping),

    # about pages
    path('about/timeline', views.timeline, name='timeline'),
    path('about/licenses/<slug:license_slug>/', views.license_content, name='license_content'),
    path('about/duas/<slug:dua_slug>/', views.dua_content, name='dua_content'),
    path('about/citi-course/', views.citi_course, name='citi_course'),

    # # Custom error pages for testing
    # path('403.html', views.error_403, name='error_403'),
    # path('404.html', views.error_404, name='error_404'),
    # path('500.html', views.error_500, name='error_500'),

    # temporary content overview pages
    path('about/content/', views.content_overview,
        name='content_overview'),
    path('about/database/', views.database_overview,
        name='database_overview'),
    path('about/software/', views.software_overview,
        name='software_overview'),

    # detailed pages related to the challenges overview
    path('about/challenge/moody-challenge-overview', views.moody_challenge_overview,
         name='moody_challenge_overview'),
    path('about/challenge/moody-challenge', views.moody_challenge,
         name='moody_challenge'),
    path('about/challenge/community-challenge', views.community_challenge,
         name='community_challenge'),

    # path for about static pages
    path('about/', views.static_view, name='static_view'),
    path('about/<path:static_url>/', views.static_view, name='static_view'),

    # robots.txt for crawlers
    path(
        'robots.txt', lambda x: HttpResponse("User-Agent: *\\Allow: /", content_type="text/plain"), name="robots_file"
    ),

    # path for the Browsable API Authentication
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),

    # path for Database List - to be deprecated soon
    path('rest/database-list/', database_list,
         name='database_list')
]

if settings.ENABLE_LIGHTWAVE:
    urlpatterns.append(path('lightwave/', include('lightwave.urls')))
    # backward compatibility for LightWAVE
    urlpatterns.append(path('cgi-bin/lightwave',
                            lightwave_views.lightwave_server,
                            name='lightwave_server_compat'))

if settings.ENABLE_SSO:
    urlpatterns.append(path('', include('sso.urls')))

if settings.ENABLE_CLOUD_RESEARCH_ENVIRONMENTS:
    urlpatterns.append(path('environments/', include('environment.urls')))

if settings.DEBUG:
    import debug_toolbar

    # debug toolbar
    urlpatterns.append(path('__debug__/', include(debug_toolbar.urls)))

# Parameters for testing URLs (see physionet/test_urls.py)
TEST_DEFAULTS = {
    'dua_slug': 'physionet-credentialed-health-data-dua',
    'event_slug': 'iLII4L9jSDFh',
    'license_slug': 'open-data-commons-attribution-license-v10',
    'static_url': 'publish',
    'news_slug': 'cloud-migration',
}
TEST_CASES = {
    'lightwave_server_compat': {
        '_skip_': lambda: (shutil.which('sandboxed-lightwave') is None),
    },
}
