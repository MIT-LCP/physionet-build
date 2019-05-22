from project.fileviews.base import FileView


class ImageFileView(FileView):
    """
    Class for displaying image files.
    """

    def render(self, request):
        return super().render(request, 'project/file_view_image.html')
