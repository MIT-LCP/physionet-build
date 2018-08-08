import os

from django.http import HttpResponse, Http404


def serve_file(request, file_path):
    """
    Serve a file to download. file_path is the full file path of the
    file on the server
    """
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read())
            response['Content-Disposition'] = 'attachment; filename=' + os.path.basename(file_path)
            return response
    else:
        return Http404()
