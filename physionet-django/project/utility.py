import datetime
import os
import shutil
import pdb
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse, Http404


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


def get_dir_breadcrumbs(subdir):
    """
    Given a subdirectory, return all breadcrumb elements

    full_subdir for inputs:
    ''  -->
    d1  --> ['', 'd1']
    d1/  --> ['', 'd1']
    d1/d2/d3
    d1/d2/d3/
    """

    if subdir == '':
        return [DirectoryBreadcrumb(name='<base>', rel_path='',
                                    full_subdir='', active=False)]
    if subdir.endswith('/'):
        subdir = subdir[:-1]
    dirs = subdir.split('/')
    rel_path = '../' * len(dirs)
    dir_breadcrumbs = [DirectoryBreadcrumb(name='<base>', full_subdir='',
                                           rel_path=rel_path)]
    for i in range(len(dirs)):
        rel_path = rel_path[3:]
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
    return sorted([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and not f.endswith('~')])


def list_directories(directory):
    "List directories in a directory"
    return sorted([d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))])

def list_items(directory, return_separate=True):
    "List files and directories in a directory. Return separate or combine lists"
    if return_separate:
        return (list_files(directory), list_directories(directory))
    else:
        return sorted(list_files(directory)+list_directories(directory))

def remove_items(items):
    """
    Delete the list of (full file path) files/directories.
    """
    for item in items:
        if os.path.isfile(item):
            os.remove(item)
        elif os.path.isdir(item):
            shutil.rmtree(item)
    return

def move_items(items, target_folder):
    """
    Move items (full path) into target folder (full path)
    """
    for item in items:
        os.rename(item, os.path.join(target_folder, os.path.split(item)[-1]))

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
