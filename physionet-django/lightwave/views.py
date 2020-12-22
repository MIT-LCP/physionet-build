import os
import re
import shutil
import subprocess

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse

from project.models import PublishedProject
from project.views import project_auth


# PUBLIC_ROOT: chroot directory for public databases
if settings.STATIC_ROOT:
    PUBLIC_ROOT = settings.STATIC_ROOT
else:
    PUBLIC_ROOT = os.path.join(settings.BASE_DIR, 'static')

# PUBLIC_DBPATH: path to main database directory within PUBLIC_ROOT
PUBLIC_DBPATH = 'published-projects'

# ORIGINAL_DBCAL_FILE: absolute path to the wfdbcal file from WFDB
ORIGINAL_DBCAL_FILE = '/usr/local/database/wfdbcal'
# DBCAL_FILE: absolute path to the public wfdbcal symlink file
DBCAL_FILE = os.path.join(PUBLIC_ROOT, 'wfdbcal')


def lightwave_home(request, project_slug, project_version):
    """
    Render LightWAVE main page for published databases.
    """
    return render(request, 'lightwave/home.html', {
        'project_slug': project_slug,
        'project_version': project_version,
        'lightwave_server_url': reverse('lightwave_server'),

        # FIXME: Scribe should be updated to save annotations to
        # logged-in user's account.  And probably we should just
        # disable editing for non-logged-in users, and tell them to
        # log in if they want to edit.

        'lightwave_scribe_url':
        'https://archive.physionet.org/cgi-bin/lw-scribe',
    })


@project_auth(auth_mode=3)
def lightwave_project_home(request, project_slug, project, **kwargs):
    """
    Render LightWAVE main page for an active project.
    """
    # FIXME: Show an error message if no RECORDS file is present.
    return render(request, 'lightwave/home.html', {
        'project_slug': project_slug,
        'project_version': '',
        'lightwave_server_url': reverse('lightwave_project_server',
                                        args=(project_slug,)),

        # FIXME: As above, need an updated scribe and a place to save
        # annotations.

        'lightwave_scribe_url': '',
    })


_lightwave_command = (shutil.which('sandboxed-lightwave'),)
_cgi_header = re.compile('(?ia)(Content-Type):\s*(.*)')


def serve_lightwave(query_string, root, dbpath='/', dblist=None, dbcal=None,
                    public=False):
    """
    Request data from the LightWAVE server.

    The server is sandboxed so that it can only access files within
    the given root directory.  By default, the root directory is also
    used as the default database path, but a different path (or
    multiple paths, separated by spaces) can be specified as dbpath.
    These paths must be accessible within the sandbox root directory.

    The list of available databases is retrieved from the DBS file by
    default; this can be overridden by specifying dblist.

    The global wfdbcal file is used by default, but can be overridden
    by specifying dbcal.  (Unlike dbpath, this path is not relative to
    the sandbox root.)

    If public is true, the data may be accessed by any web page,
    either using XMLHttpRequest or using JSONP.  If public is false,
    the data may be accessed only by same-origin pages.
    """

    # This function implements an extremely basic subset of CGI - just
    # enough to be compatible with lightwave.  In particular: none of
    # the CGI variables other than QUERY_STRING are provided, and only
    # the Content-Type header is supported.

    env = {
        'WFDB': dbpath,
        'LIGHTWAVE_ROOT': root,
        'QUERY_STRING': query_string,
        'LIGHTWAVE_WFDBCAL': (dbcal or DBCAL_FILE),
    }
    if dblist:
        env['LIGHTWAVE_DBLIST'] = dblist

    resp = HttpResponse()
    if public:
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Headers'] = 'x-requested-with'
    else:
        env['LIGHTWAVE_DISABLE_JSONP'] = '1'

    with subprocess.Popen(_lightwave_command, close_fds=True, env=env,
                          stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE) as proc:
        for line in proc.stdout:
            line = line.rstrip(b'\n\r').decode()
            if line == '':
                break
            m = _cgi_header.match(line)
            if m:
                resp[m.group(1)] = m.group(2)
        else:
            raise Exception('no response header')
        resp.write(proc.stdout.read())
    return resp


def lightwave_server(request):
    """
    Request LightWAVE data for a published database.
    """
    if request.GET.get('action', '') == 'dblist':
        projects = PublishedProject.objects.filter(
            has_wfdb=True, access_policy=0, deprecated_files=False).order_by(
            'title', '-version_order')
        dblist = '\n'.join(
            '{}/{}\t{}'.format(p.slug, p.version, p) for p in projects)
    else:
        dblist = None
    return serve_lightwave(query_string=request.GET.urlencode(),
                           root=PUBLIC_ROOT,
                           dbpath=PUBLIC_DBPATH,
                           dblist=dblist,
                           public=True)


@project_auth(auth_mode=3)
def lightwave_project_server(request, project_slug, project, **kwargs):
    """
    Request LightWAVE data for an active project.
    """
    # Kludge: override the db parameter in the URL, since we are
    # chrooting to project.file_root(), but the client should see each
    # project as a distinct database for annotation purposes
    return serve_lightwave(query_string=('db=.&' + request.GET.urlencode()),
                           root=project.file_root(),
                           dblist=(project_slug + '\t' + project.title),
                           public=False)
