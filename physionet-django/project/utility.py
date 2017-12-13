import datetime
import os

from .models import FileInfo, DirectoryInfo


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


def get_dir_size(base_dir):
    "Total size of a directory in bytes"
    total_size = 0
    for (path, dirs, files) in os.walk(base_dir):
        for file in files:
            filename = os.path.join(path, file)
            total_size += os.path.getsize(filename)
    return total_size


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
