from __future__ import unicode_literals
from django.db import models
from users.models import User
from .models import DisplayFile, DisplayDirectory
import os
import datetime


# Given a file path, get the information used to display it
def get_display_file(filepath):
    name = os.path.split(filepath)[-1]
    size = readable_size(os.path.getsize(filepath))
    lastmtime = datetime.date.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d")
    description = ''

    return DisplayFile(name, size, lastmtime, description)


def get_display_directory(dirpath):
    name = os.path.split(dirpath)[-1]
    size = ''
    lastmtime = datetime.date.fromtimestamp(os.path.getmtime(dirpath)).strftime("%Y-%m-%d")
    description = ''

    return DisplayDirectory(name, size, lastmtime, description)

def readable_size(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024:
            readsize = '{0:g}'.format(num)

            if '.' not in readsize:
                return readsize+' '+unit+suffix
            else: 
                return "%3.1f %s%s" % (num, unit, suffix)
            
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix)