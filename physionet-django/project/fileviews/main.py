from errno import ENAMETOOLONG
import os

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect

from physionet.gcp import ObjectPath
from project.fileviews.base import RawFileView
from project.fileviews.csv import CSVFileView, GzippedCSVFileView
from project.fileviews.image import ImageFileView
from project.fileviews.inline import InlineFileView
from project.fileviews.text import TextFileView

_suffixes = {
    '.bmp': ImageFileView,
    '.csv': CSVFileView,
    '.gif': ImageFileView,
    '.htm': RawFileView,
    '.html': RawFileView,
    '.jpeg': ImageFileView,
    '.jpg': ImageFileView,
    '.png': ImageFileView,
    '.pdf': InlineFileView,
    '.svg': ImageFileView,
}


def display_project_file(request, project, file_path):
    """
    Display a file from either a published or unpublished project.

    The user is assumed to be authorized to view the project.
    file_path is the name of the file relative to project.file_root().
    """

    try:
        abs_path = os.path.join(project.file_root(), file_path)

        if settings.STORAGE_TYPE == 'LOCAL':
            infile = open(abs_path, 'rb')
            size = os.stat(infile.fileno()).st_size
        elif settings.STORAGE_TYPE == 'GCP':
            infile = ObjectPath(abs_path).open('rb')
            size = infile.size
    except IsADirectoryError:
        return redirect(request.path + '/')
    except (FileNotFoundError, NotADirectoryError):
        raise Http404()
    except (IOError, OSError) as err:
        raise (Http404() if err.errno == ENAMETOOLONG else err)

    with infile:
        if file_path.endswith('.csv.gz'):
            cls = GzippedCSVFileView
        else:
            (_, suffix) = os.path.splitext(file_path)
            cls = _suffixes.get(suffix, TextFileView)
        view = cls(project, file_path, infile, size)
        return view.render(request)
