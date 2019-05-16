import os
import zipfile

from django.conf import settings
from django.http import HttpResponse, Http404


def get_project_apps():
    """
    Return a string list of all the apps in this django project
    """
    return [app for app in settings.INSTALLED_APPS if not app.startswith('django') and not app.startswith('ck') and not app.startswith('debug')]

def _file_x_accel_path(file_path):
    static_root = settings.STATIC_ROOT
    media_root = settings.MEDIA_ROOT
    media_alias = settings.MEDIA_X_ACCEL_ALIAS
    if media_alias:
        if file_path.startswith(static_root + '/'):
            return '/static' + file_path[len(static_root):]
        elif file_path.startswith(media_root + '/'):
            return media_alias + file_path[len(media_root):]

def serve_file(file_path, attach=True):
    """
    Serve a file to download. file_path is the real path of the file on
    the server.
    """
    accel_path = _file_x_accel_path(file_path)
    if accel_path:
        response = HttpResponse()
        response['X-Accel-Redirect'] = accel_path
    else:
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read())
    base = os.path.basename(file_path)
    response['Content-Type'] = ''
    if attach:
        response['Content-Disposition'] = 'attachment; filename=' + base
    else:
        response['Content-Disposition'] = 'inline; filename=' + base
    return response

def zip_dir(zip_name, target_dir, enclosing_folder=''):
    """
    Recursively zip contents in a directory.

    Parameters
    ----------
    zip_name : file name of the output zip file.
    target_dir : full path of directory to zip.
    enclosed_folder : enclosing folder name to write within zip file.
    """
    if target_dir.endswith('/'):
        target_dir = target_dir.rstrip('/')

    with zipfile.ZipFile(zip_name, 'w') as zipf:
        for root, dirs, files in os.walk(target_dir):
            for file in files:
                # Do not include the path to the target directory when
                # writing files in the zip
                zipf.write(os.path.join(root, file),
                    arcname=os.path.join(enclosing_folder,
                    root[len(target_dir)+1:], file))
