from project.fileviews.base import FileView


class InlineFileView(FileView):
    """
    Class for displaying inline documents.
    """

    def render(self, request):
        return super().render(request, 'project/file_view_inline.html')
