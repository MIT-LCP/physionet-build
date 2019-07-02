import os
import shutil
import subprocess
import tempfile

from django.conf import settings
from django.http import HttpResponse, Http404
from django.utils.html import format_html

CONTENT_TYPE = {
    '.html': 'text/html',
    '.htm': 'text/html',

    '.gif': 'image/gif',
    '.jpeg': 'image/jpeg',
    '.jpg': 'image/jpeg',
    '.png': 'image/png',
    '.tif': 'image/tiff',
    '.tiff': 'image/tiff',
    '.wbmp': 'image/vnd.wap.wbmp',
    '.ico': 'image/x-icon',
    '.jng': 'image/x-jng',
    '.bmp': 'image/x-ms-bmp',
    '.svg': 'image/svg+xml',
    '.svgz': 'image/svg+xml',
    '.webp': 'image/webp',

    '.pdf': 'application/pdf',

    '.zip': 'application/zip',
    '.tar': 'application/x-tar',
    '.gz': 'application/gzip',
    '.bz2': 'application/x-bzip2',
    '.xz': 'application/x-xz',

    '.16a': 'application/octet-stream',
    '.16a': 'application/octet-stream',
    '.abp': 'application/octet-stream',
    '.al': 'application/octet-stream',
    '.all': 'application/octet-stream',
    '.apn': 'application/octet-stream',
    '.ari': 'application/octet-stream',
    '.arou': 'application/octet-stream',
    '.atr': 'application/octet-stream',
    '.cvp': 'application/octet-stream',
    '.dat': 'application/octet-stream',
    '.ecg': 'application/octet-stream',
    '.edf': 'application/octet-stream',
    '.hyp': 'application/octet-stream',
    '.hypn': 'application/octet-stream',
    '.in': 'application/octet-stream',
    '.let': 'application/octet-stream',
    '.not': 'application/octet-stream',
    '.oart': 'application/octet-stream',
    '.pap': 'application/octet-stream',
    '.ple': 'application/octet-stream',
    '.pu': 'application/octet-stream',
    '.pu0': 'application/octet-stream',
    '.pu1': 'application/octet-stream',
    '.q1c': 'application/octet-stream',
    '.q2c': 'application/octet-stream',
    '.qrs': 'application/octet-stream',
    '.qrsc': 'application/octet-stream',
    '.qt1': 'application/octet-stream',
    '.qt2': 'application/octet-stream',
    '.rec': 'application/octet-stream',
    '.resp': 'application/octet-stream',
    '.rit': 'application/octet-stream',
    '.st': 'application/octet-stream',
    '.st-': 'application/octet-stream',
    '.str': 'application/octet-stream',
    '.trigger': 'application/octet-stream',
}

def get_project_apps():
    """
    Return a string list of all the apps in this django project
    """
    return [app for app in settings.INSTALLED_APPS if not app.startswith('django') and not app.startswith('ck') and not app.startswith('debug')]

def file_content_type(filename):
    (_, ext) = os.path.splitext(filename)
    return CONTENT_TYPE.get(ext, 'text/plain')

def _file_x_accel_path(file_path):
    static_root = settings.STATIC_ROOT
    media_root = settings.MEDIA_ROOT
    media_alias = settings.MEDIA_X_ACCEL_ALIAS
    if media_alias:
        if file_path.startswith(static_root + '/'):
            return '/static' + file_path[len(static_root):]
        elif file_path.startswith(media_root + '/'):
            return media_alias + file_path[len(media_root):]

def serve_file(file_path, attach=True, allow_directory=False):
    """
    Serve a file to download. file_path is the real path of the file on
    the server.

    If allow_directory is true and file_path ends with a slash, serve
    a simple HTML directory listing.
    """
    accel_path = _file_x_accel_path(file_path)
    if accel_path:
        response = HttpResponse()
        response['X-Accel-Redirect'] = accel_path
        response['Content-Type'] = ''
    else:
        if file_path.endswith('/') and allow_directory:
            html = '<!DOCTYPE html><html><body><ul>\n'
            for f in sorted(os.listdir(file_path)):
                html += format_html('<li><a href="{0}">{0}</a></li>\n', f)
            html += '</ul></body></html>'
            return HttpResponse(html)
        else:
            with open(file_path, 'rb') as f:
                response = HttpResponse(f.read())
                response['Content-Type'] = file_content_type(file_path)
    base = os.path.basename(file_path)
    if attach:
        response['Content-Disposition'] = 'attachment; filename=' + base
    else:
        response['Content-Disposition'] = 'inline; filename=' + base
    return response


def sorted_tree_files(directory, *, prefix=''):
    """
    Return the recursive contents of a directory in order.

    Paths are sorted in byte order, and only regular files are
    returned (similar to 'find . -type f | LC_COLLATE=C sort').  For
    example:

    >>> import os
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     os.system('cd %s; mkdir a c; touch B a+ a/2 a/10 ab' % d)
    ...     list(sorted_tree_files(d))
    0
    ['B', 'a+', 'a/10', 'a/2', 'ab']
    """
    contents = []
    for e in os.scandir(directory):
        if e.is_dir(follow_symlinks=False):
            contents.append(e.name + '/')
        elif e.is_file(follow_symlinks=False):
            contents.append(e.name)
    contents.sort()
    for name in contents:
        path = prefix + name
        if name.endswith('/'):
            yield from sorted_tree_files(os.path.join(directory, name),
                                         prefix=path)
        else:
            yield path


def zip_dir(zip_name, target_dir, enclosing_folder=''):
    """
    Recursively zip contents in a directory.

    Parameters
    ----------
    zip_name : file name of the output zip file.
    target_dir : full path of directory to zip.
    enclosed_folder : enclosing folder name to write within zip file.
    """

    # We use the 'zip' command here, rather than the zipfile library,
    # because:
    #  * zip supports multiple compression levels
    #  * zip will automatically store files uncompressed if "deflate"
    #    doesn't give any benefit

    tmp_dir = None
    try:
        # If enclosing_folder is specified, temporarily create a
        # symbolic link with that name that can be passed to 'zip'
        if enclosing_folder:
            tmp_dir = tempfile.mkdtemp()
            os.symlink(os.path.realpath(target_dir),
                       os.path.join(tmp_dir, enclosing_folder))
            working_dir = tmp_dir
            prefix = enclosing_folder + '/'
        else:
            working_dir = target_dir
            prefix = ''

        # Write the archive to a temporary file; delete that file if
        # it already exists so that 'zip' won't try to update an
        # existing archive
        tmp_zip_name = zip_name + '.tmp'
        try:
            os.remove(tmp_zip_name)
        except FileNotFoundError:
            pass

        # Invoke 'zip' and pass the sorted list of files to its
        # standard input
        command = ('zip', '-q', '-X', '-9',
                   os.path.realpath(tmp_zip_name), '-@')
        with subprocess.Popen(command, cwd=working_dir,
                              stdin=subprocess.PIPE) as proc:
            for path in sorted_tree_files(target_dir, prefix=prefix):
                # File names that include \n or \r (which could be
                # used to trick 'zip' into reading files from
                # elsewhere on the system) are silently ignored.
                if '\n' not in path and '\r' not in path:
                    proc.stdin.write(path.encode() + b'\n')
            proc.stdin.close()
            if proc.wait() != 0:
                raise subprocess.CalledProcessError(proc.returncode, command)

        # Rename the temporary file to the target filename
        os.rename(tmp_zip_name, zip_name)

    finally:
        # Remove the temporary directory and/or temporary zip file
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            os.remove(tmp_zip_name)
        except FileNotFoundError:
            pass
