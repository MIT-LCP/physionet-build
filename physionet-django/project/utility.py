import datetime
import errno
import os
import shutil
import pdb
import uuid
import logging
import requests
import json

from django.contrib import messages
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse, Http404

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
    def __init__(self, allowance, used, include_remaining,
        main_used=None, compressed_used=None):
        """
        Initialize fields with optional args for published and
        unpublished projects
        """
        self.allowance = allowance
        self.readable_allowance = readable_size(allowance)

        # Total used
        self.used = used
        self.readable_used = readable_size(used)

        if include_remaining:
            remaining = allowance - used
            self.remaining = remaining
            self.readable_remaining = readable_size(remaining)
            self.p_used = round(used *100 / allowance)
            self.p_remaining = round(remaining *100 / allowance)

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
    """
    for item in items:
        try:
            os.remove(item)
        except IsADirectoryError:
            shutil.rmtree(item)
        except FileNotFoundError:
            if not ignore_missing:
                raise

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

def get_tree_files(path, full_path=True):
    """
    Return list of files from a base path
    """
    files = []
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            files += get_tree_files(entry.path, full_path=True)
        else:
            files.append(entry.path)
    # Strip the original path if desired
    if not full_path:
        if not path.endswith('/'):
            path += '/'
        files = [f[len(path):] for f in files]
    return files

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
    # The paylod has to be a string in an array
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

def grant_gcp_group_access(user, project, data_access):
    """
    Funtion to add a specific email address to a organizational google group
    Returns two things:
        The first argunet is if acces was awarded.
        The second argunet is if the access was awarded in a previous time.
    """
    email = user.cloud_information.gcp_email.email
    service = create_directory_service(settings.GCP_DELEGATION_EMAIL)
    for item in data_access:
        members = service.members().list(groupKey=item.location).execute()
        access = "Access to the GCP BigQuery"
        if data_access == 3:
            access = "Access to the GCP bucket"
        if email not in str(members):
            # if not a member, add to the group
            outcome = service.members().insert(groupKey=item.location,
                body={"email": email, "delivery_settings": "NONE"}).execute()
            if outcome['role'] == "MEMBER":
                messages.success(request, '{0} has been granted \
                    to {1} for project: {2}'.format(access, email, project))
                LOGGER.info("Added user {0} to BigQuery group {1}".format(
                    email, item.location))
                return True
            else:
                messages.success(request, 'There was an error granting \
                    access.')
                LOGGER.info("Error adding the user {0} to Bigquery group \
                    {1}. Error: {2}".format(email, item.location, outcome))
        else:
            messages.success(request, '{0} was previously awarded \
                to {1} for project: {2}'.format(access, email, project))
            return False
