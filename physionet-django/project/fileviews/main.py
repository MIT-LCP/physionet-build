from errno import ENAMETOOLONG
import os

from physionet import aws
from django.conf import settings
import botocore

from django.http import Http404
from django.shortcuts import redirect

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
        if settings.STORAGE_TYPE == 'LOCAL':
            abs_path = os.path.join(project.file_root(), file_path)
            infile = open(abs_path, 'rb')
            size = os.stat(file.fileno()).st_size
        else:
            abs_path = os.path.join('active-projects', project.slug, file_path)
            print('Display:', abs_path)
            obj = aws.get_s3_resource().meta.client.get_object(Bucket='hdn-data-platform-media', Key=abs_path)
            infile = obj['Body']
            size = obj['ContentLength']
    except IsADirectoryError:
        return redirect(request.path + '/')
    except (FileNotFoundError, NotADirectoryError, botocore.exceptions.ClientError):
        raise Http404()
    except (IOError, OSError) as err:
        if err.errno == ENAMETOOLONG:
            raise Http404()
        else:
            raise err

    # with infile:
    if file_path.endswith('.csv.gz'):
        cls = GzippedCSVFileView
    else:
        (_, suffix) = os.path.splitext(file_path)
        cls = _suffixes.get(suffix, TextFileView)
    view = cls(project, file_path, infile, size)
    return view.render(request)
