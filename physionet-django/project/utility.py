import base64
import datetime
import errno
import os
import shutil
import pdb
import uuid
import logging
import re
import requests
import json

from django.contrib import auth, messages
from django.contrib.sites.shortcuts import get_current_site
from django.conf import settings
from django.core.exceptions import (PermissionDenied, ValidationError)
from django.http import HttpResponse, Http404
from googleapiclient.errors import HttpError

from console.utility import create_directory_service

LOGGER = logging.getLogger(__name__)

class FileInfo():
    """
    For displaying lists of files in project pages
    All attributes are human readable strings
    """
    def __init__(self, name, size, last_modified):
        self.name = name
        self.size = size
        self.last_modified= last_modified


class DirectoryInfo():
     def __init__(self, name):
        self.name = name


class DirectoryBreadcrumb():
    """
    For navigating through project file directories
    """
    def __init__(self, name, rel_path, full_subdir, active=True):
        self.name = name
        self.rel_path = rel_path
        self.full_subdir = full_subdir
        self.active = active


def get_dir_breadcrumbs(path, directory=True):
    """
    Given a subdirectory, return all breadcrumb elements

    full_subdir for inputs:
    ''  -->
    d1  --> ['', 'd1']
    d1/  --> ['', 'd1']
    d1/d2/d3
    d1/d2/d3/
    """

    if path == '':
        return [DirectoryBreadcrumb(name='<base>', rel_path='',
                                    full_subdir='', active=False)]
    if path.endswith('/'):
        path = path[:-1]
    dirs = path.split('/')
    rel_path = '../' * len(dirs)
    if not directory:
        rel_path = (rel_path[3:] or './')
    dir_breadcrumbs = [DirectoryBreadcrumb(name='<base>', full_subdir='',
                                           rel_path=rel_path)]
    for i in range(len(dirs)):
        rel_path = (rel_path[3:] or './')
        dir_breadcrumbs.append(DirectoryBreadcrumb(
            name=dirs[i], rel_path=rel_path,
            full_subdir='/'.join([d.name for d in dir_breadcrumbs[1:]]+ [dirs[i]])))
    dir_breadcrumbs[-1].active = False
    return dir_breadcrumbs


class StorageInfo():
    """
    Object for storing display information about a project's storage.
    """
    def __init__(self, allowance, used, include_remaining=True,
        main_used=None, compressed_used=None):
        """
        Initialize fields with optional args for published and
        unpublished projects

        The include_remaining argument has no effect and is kept for
        compatibility.
        """
        self.allowance = allowance
        self.readable_allowance = readable_size(allowance)

        # Total used
        self.used = used
        if used is None:
            self.readable_used = 'unknown'
            self.remaining = None
            self.readable_remaining = 'unknown'
            self.p_used = '?'
            self.p_remaining = '?'
        else:
            self.readable_used = readable_size(used)
            self.remaining = allowance - used
            self.readable_remaining = readable_size(self.remaining)
            self.p_used = round(used * 100 / allowance)
            self.p_remaining = round(self.remaining * 100 / allowance)

        if main_used is not None:
            self.main_used = main_used
            self.readable_main_used = readable_size(main_used)

        if compressed_used is not None:
            self.compressed_used = compressed_used
            self.readable_compressed_used = readable_size(compressed_used)


def list_files(directory):
    "List files in a directory"
    files = []
    for ent in os.scandir(directory):
        if not ent.is_dir():
            files.append(ent.name)
    return sorted(files)


def list_directories(directory):
    "List directories in a directory"
    dirs = []
    for ent in os.scandir(directory):
        if ent.is_dir():
            dirs.append(ent.name)
    return sorted(dirs)


def list_items(directory, return_separate=True):
    "List files and directories in a directory. Return separate or combine lists"
    if return_separate:
        dirs = []
        files = []
        for ent in os.scandir(directory):
            if ent.is_dir():
                dirs.append(ent.name)
            else:
                files.append(ent.name)
        return (sorted(files), sorted(dirs))
    else:
        return sorted(os.listdir(directory))

def remove_items(items, ignore_missing=True):
    """
    Delete the list of (full file path) files/directories.

    Args:
      items: Is a list of files or directories to delete.
      ignore_missing: Flag to ignore missing files or directories.
    """
    if isinstance(items,(tuple,list)):
        for item in items:
            try:
                os.unlink(item)
            except FileNotFoundError:
                if not ignore_missing:
                    raise
            except OSError as e:
                if e.errno not in (errno.EISDIR, errno.EPERM):
                    raise
                shutil.rmtree(item)
    else:
        LOGGER.info("Non list/tuple entered in remove items. The 'item' entered \
         was: {0}".format(items))
        raise TypeError

def clear_directory(directory):
    """
    Delete all files and folders in a directory.
    """
    remove_items(os.path.join(directory, i) for i in os.listdir(directory))

def rename_file(old_path, new_path):
    """
    Rename a file, without overwriting an existing file.

    If the destination path already exists, this will attempt to raise
    a FileExistsError.  This is not guaranteed to work correctly in
    all cases.
    """
    if os.path.exists(new_path):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST),
                              old_path, new_path)
    os.rename(old_path, new_path)

def move_items(items, target_folder):
    """
    Move items (full path) into target folder (full path)
    """
    for item in items:
        rename_file(item, os.path.join(target_folder, os.path.split(item)[-1]))

def get_file_info(file_path):
    "Given a file path, get the information used to display it"
    name = os.path.split(file_path)[-1]
    size = readable_size(os.path.getsize(file_path))
    last_modified = datetime.date.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d")
    return FileInfo(name, size, last_modified)

def get_directory_info(dir_path):
    "Given a directory path, get the information used to display it"
    return DirectoryInfo(os.path.split(dir_path)[-1])

def get_tree_size(path):
    """Return total size of files in given path and subdirs."""
    total = 0
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            total += get_tree_size(entry.path)
        else:
            total += entry.stat(follow_symlinks=False).st_size
    return total


def readable_size(num, suffix='B'):
    "Display human readable size of byte number"
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024:
            readsize = '{0:g}'.format(num)

            if '.' not in readsize:
                return readsize+' '+unit+suffix
            else:
                return '{:3.1f} {:s}{:s}'.format(num, unit, suffix)

        num /= 1024.0
    return '{:.1f}{:s}{:s}'.format(num, 'Y', suffix)


def write_uploaded_file(file, write_file_path, overwrite=True):
    """
    file: request.FILE
    write_file_path: full file path to be written
    """
    if overwrite:
        try:
            os.unlink(write_file_path)
        except FileNotFoundError:
            pass
    with open(write_file_path, 'xb') as destination:
        for chunk in file.chunks():
            destination.write(chunk)


def get_form_errors(form):
    """
    Extract all errors from a form eith errors
    """
    all_errors = []
    for field in form.errors:
        all_errors += form.errors[field]
    return all_errors

def grant_aws_open_data_access(user, project):
    """
    Function to grant a AWS ID access to the bukets in the Open Data
    AWS platform.
    """
    url = settings.AWS_CLOUD_FORMATION
    # The payload has to be a string in an array
    payload = {'accountid': ["{}".format(user.cloud_information.aws_id)]}
    # Custom headers set as a key for a lambda function in AWS to grant access
    headers = {settings.AWS_HEADER_KEY: settings.AWS_HEADER_VALUE,
        settings.AWS_HEADER_KEY2: settings.AWS_HEADER_VALUE2}
    # Do a request to AWS and try to add the user ID to the bucket
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    message = response.json()['message'].split(',')[0]
    # The message can differ if the ID is already there, or non-existent
    LOGGER.info("AWS message '{0}' for project {1}".format(
        response.json()['message'], project))
    return message

def grant_gcp_group_access(user, project, data_access, request):
    """
    Add a specific email address to a organizational google group
    Returns two things:
        The first argument is if access was awarded.
        The second argument is if the access was awarded in a previous time.
    """
    email = user.cloud_information.gcp_email.email
    service = create_directory_service(settings.GCP_DELEGATION_EMAIL)
    # Get all the members of the Google group
    members = service.members().list(groupKey=data_access.location).execute()
    # Set the type of access depending on the  request
    # Access == 3 is for the GCP Bucket
    # Access == 4 is for the GCP Big Query
    access = "Access to the GCP BigQuery"
    if data_access == 3:
        access = "Access to the GCP bucket"
    if email not in str(members):
        # if not a member, add to the group
        try:
            outcome = service.members().insert(groupKey=data_access.location, 
                body={"email": email, "delivery_settings": "NONE"}).execute()
            if outcome['role'] == "MEMBER":
                messages.success(request, '{0} has been granted \
                    to {1} for project: {2}'.format(access, email, project))
                LOGGER.info("Added user {0} to BigQuery group {1}".format(
                    email, data_access.location))
                return True
        except HttpError as e:
            if json.loads(e.content)['error']['message'] == 'Member already exists.':
                messages.success(request, '{0} was previously awarded \
                    to {1} for project: {2}'.format(access, email, project))
                return False
            else:
                raise e
        else:
            messages.success(request, 'There was an error granting \
                access.')
            LOGGER.info("Error adding the user {0} to Bigquery group \
                {1}. Error: {2}".format(email, data_access.location, outcome))
    else:
        messages.success(request, '{0} was previously awarded \
            to {1} for project: {2}'.format(access, email, project))
        return False


# The following regular expression defines user agents that are
# permitted to use HTTP authentication for accessing protected
# databases.  This list should not include web browsers.  (If you are
# writing a new program for accessing protected databases, please use
# a distinctive UA string so that your program can be whitelisted
# here.  Do not use the generic UA string provided by your HTTP client
# library.)
HTTP_AUTH_USER_AGENT = re.compile('|'.join((
    'Wget/',
    'libwfdb/',
    'QueryBuilder',
)))


def http_auth_allowed(request):
    """
    Check if HTTP authentication is permitted for the given request.

    Web browsers typically don't implement HTTP authentication in a
    very user-friendly or secure way, so this mechanism is only
    permitted for specific non-interactive user agents.  For safety,
    HTTP authentication is only permitted for GET and HEAD requests,
    and (unless settings.DEBUG is set) only via HTTPS.
    """

    if request.method not in ('GET', 'HEAD'):
        return False
    if not request.is_secure() and not settings.DEBUG:
        return False

    ua = request.META.get('HTTP_USER_AGENT', '')
    if HTTP_AUTH_USER_AGENT.match(ua):
        return True
    else:
        return False


def check_http_auth(request):
    """
    Check if a request includes HTTP authentication.

    If HTTP authentication is permitted for the given request, and a
    valid username and password are provided, set request.user to the
    corresponding user object.  Otherwise, the request is not
    modified.

    For safety, HTTP authentication is only used for certain requests
    from non-interactive user agents; see http_auth_allowed().

    This should be invoked at the start of the view before checking
    user credentials, and should be paired with require_http_auth().
    """

    if 'HTTP_AUTHORIZATION' in request.META:
        # If an Authorization header is supplied, but this request is
        # not allowed to use HTTP authentication, ignore the header.
        if not http_auth_allowed(request):
            return

        # If the user is already authenticated, ignore the header.
        if request.user.is_authenticated:
            return

        tokens = request.META['HTTP_AUTHORIZATION'].split()
        if len(tokens) == 2 and tokens[0].lower() == 'basic':
            try:
                data = base64.b64decode(tokens[1], validate=True).decode()
                username, password = data.split(':', 1)
            except Exception:
                return

            user = auth.authenticate(request=request,
                                     username=username,
                                     password=password)
            if user:
                request.user = user


def require_http_auth(request):
    """
    Ask the client to authenticate itself and retry the request.

    For safety, HTTP authentication is only allowed for certain
    requests from non-interactive user agents; see
    http_auth_allowed().  If this request is not allowed, or if the
    user is already authenticated, raise PermissionDenied.

    Otherwise, return an HttpResponse with status 401 (Unauthorized),
    which indicates the client should repeat the request with a
    username and password.

    This should be invoked after check_http_auth(), if the user is
    unknown or is not authorized to view the given resource.
    """

    if http_auth_allowed(request) and not request.user.is_authenticated:
        site = get_current_site(request)
        response = HttpResponse(status=401)
        response['WWW-Authenticate'] = (
            'Basic realm="{}", charset="UTF-8"'.format(site.name)
        )
        return response
    else:
        raise PermissionDenied()
