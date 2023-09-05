import gzip
import os

from django.shortcuts import redirect, render
from django.urls import reverse
from physionet.utility import file_content_type
from project.utility import get_dir_breadcrumbs

MAX_PLAIN_SIZE = 5 * 1024 * 1024


class FileView:
    """
    Base class for displaying file content.

    To display a file in response to an HTTP request, create an
    appropriate FileView object and invoke render().

    The base implementation displays "This file cannot be viewed in
    the browser."  Subclasses will typically override render() to
    display something more useful.
    """

    def __init__(self, project, path, file):
        self.project = project
        self.path = path
        self.file = file
        self._basename = os.path.basename(path)
        self._size = file.size
        self._url = project.file_url('', path)

    def render(self, request, template='project/file_view.html',
               show_plain=None, **template_args):
        """
        Render the file to an HttpResponse.
        """

        if self.size() == 0:
            template = 'project/file_view_empty.html'
            show_plain = False
        elif show_plain is None:
            if self.size() <= MAX_PLAIN_SIZE:
                ctype = file_content_type(self.path)
                show_plain = ctype.startswith('text/')

        breadcrumbs = get_dir_breadcrumbs(self.path, directory=False)

        # If '?return=files' is specified, make breadcrumb links point
        # back to project_files rather than to project_preview.  This
        # only makes sense for active (unpublished) projects.
        if (request.GET.get('return') == 'files'
                and not hasattr(self.project, 'publish_datetime')):
            base_url = reverse('project_files', args=(self.project.slug,))
            for b in breadcrumbs:
                b.rel_path = os.path.join(base_url, b.full_subdir, '')

        response = render(request, template, {
            'breadcrumbs': breadcrumbs,
            'file': self,
            'project': self.project,
            'show_plain': show_plain,
            **template_args
        })

        # override the default filename used when saving the page from
        # the browser (esp. when right-clicking a link)
        response['Content-Disposition'] = ('inline; filename='
                                           + self._basename + '.html')
        return response

    def basename(self):
        """
        Return the basename of the file.
        """
        return self._basename

    def display_size(self):
        """
        Return a human-readable file size.
        """
        return '{:,} bytes'.format(self.size())

    def download_url(self):
        """
        Return a URL that can be used to download the file.

        This URL points to the raw file, but with an extra query
        parameter indicating that we should try to force the browser
        to save the file rather than displaying it.
        """
        return self.project.files.download_url(self.project, self.path)

    def raw_url(self):
        """
        Return a URL that can be used to view the file.

        This URL points to the raw file and will be displayed
        according to the browser's default settings for the
        corresponding content type.
        """
        return self.project.files.raw_url(self.project, self.path)

    def size(self):
        """
        Return the size of the file in bytes.
        """
        return self._size


class RawFileView(FileView):
    """
    Class for displaying file verbatim.

    Instead of rendering an HTML page to display the file, the client
    is redirected to the raw file itself.  This is suitable for HTML
    and not much else.
    """

    def render(self, request):
        return redirect(self.raw_url())


class GzippedFileView:
    """
    Mix-in class for displaying gzip-compressed file content.
    """

    def render(self, request, *args, **kwargs):
        self.compressed_file = self.file
        try:
            with gzip.GzipFile(fileobj=self.compressed_file) as self.file:
                return super().render(request, *args, **kwargs)
        except OSError:
            return FileView.render(self, request, show_plain=False)
