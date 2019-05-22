import os

from django.http import Http404
from django.shortcuts import redirect

from physionet.utility import serve_file
from project.utility import get_dir_breadcrumbs, file_content_type
from project.fileviews.base import render_unknown, render_empty, render_raw
from project.fileviews.text import render_text
from project.fileviews.csv import render_csv, render_csv_gz
from project.fileviews.image import render_image

MAX_PLAIN_SIZE = 5 * 1024 * 1024

_suffixes = {
    '.csv': render_csv,
    '.png': render_image,
    '.jpg': render_image,
    '.jpeg': render_image,
    '.gif': render_image,
    '.bmp': render_image,
    '.svg': render_image,
    '.htm': render_raw,
    '.html': render_raw,
}


def display_project_file(request, project, file_path):
    """
    Display a file from either a published or unpublished project.

    The user is assumed to be authorized to view the project.
    file_path is the name of the file relative to project.file_root().
    """

    try:
        abs_path = os.path.join(project.file_root(), file_path)

        with open(abs_path, 'rb') as infile:
            stat = os.stat(infile.fileno())
            size = stat.st_size
            file_size = '{:,} bytes'.format(size)

            file_basename = os.path.basename(file_path)
            breadcrumbs = get_dir_breadcrumbs(file_path, directory=False)

            context = {
                'breadcrumbs': breadcrumbs,
                'file_basename': file_basename,
                'file_path': file_path,
                'file_size': file_size,
                'project': project,
                'size': size,
            }

            url = project.file_url('', file_path)
            context['file_raw_url'] = url
            context['file_download_url'] = url + '?download'

            ctype = file_content_type(file_path)
            if size <= MAX_PLAIN_SIZE and ctype.startswith('text/'):
                context['show_plain'] = True

            print(ctype)

            if size == 0:
                response = render_empty(request, infile, context)
            else:
                (_, suffix) = os.path.splitext(file_basename)
                func = _suffixes.get(suffix)
                if func:
                    response = func(request, infile, context)
                elif file_basename.endswith('.csv.gz'):
                    response = render_csv_gz(request, infile, context)
                elif ctype.startswith('text/'):
                    response = render_text(request, infile, context)
                else:
                    response = render_unknown(request, infile, context)

            response['Content-Disposition'] = ('inline; filename='
                                               + file_basename + '.html')
            return response

    except IsADirectoryError:
        return redirect(request.path + '/')
    except FileNotFoundError:
        raise Http404()
