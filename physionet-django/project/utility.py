import datetime
import os
import shutil
import pdb

class FileInfo():
    """
    For displaying lists of files in project pages
    All attributes are human readable strings
    """
    def __init__(self, name, size, last_modified, description):
        self.name = name
        self.size = size
        self.last_modified= last_modified
        self.description = description


class DirectoryInfo():
     def __init__(self, name, size, last_modified, description):
        self.name = name
        self.size = size
        self.last_modified = last_modified
        self.description = description 


class StorageInfo():
    """
    Information about a project's storage allowance, usage, and remaining.
    """
    def __init__(self, allowance, used, remaining, readable_allowance,
        readable_used, readable_remaining, p_used, p_remaining):
        # Integer fields
        self.allowance = allowance
        self.used = used
        self.remaining = remaining

        # Readable string fields
        self.readable_allowance = readable_allowance
        self.readable_used = readable_used
        self.readable_remaining = readable_remaining

        # Integer fields
        self.p_used = p_used
        self.p_remaining = p_remaining


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
        return list_files(directory)+list_directories(directory)


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
    description = ''
    return FileInfo(name, size, last_modified, description)


def get_directory_info(dir_path):
    "Given a directory path, get the information used to display it"
    name = os.path.split(dir_path)[-1]
    size = ''
    last_modified = datetime.date.fromtimestamp(os.path.getmtime(dir_path)).strftime("%Y-%m-%d")
    description = ''
    return DirectoryInfo(name, size, last_modified, description)


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
                return "%3.1f %s%s" % (num, unit, suffix)

        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix)


def get_storage_info(allowance, used):
    """
    Get information about storage allowance, usage, and remaining.
    Input variables are integers in bytes.
    """
    remaining = allowance - used
    p_used = round(used *100 / allowance)
    p_remaining = round(remaining *100 / allowance)

    return StorageInfo(allowance, used, remaining, readable_size(allowance),
        readable_size(used), readable_size(remaining), p_used, p_remaining)


def write_uploaded_file(file, write_file_path):
    """
    file: request.FILE
    write_file_path: full file path to be written
    """
    with open(write_file_path, 'wb+') as destination:
        for chunk in file.chunks():
            destination.write(chunk)
