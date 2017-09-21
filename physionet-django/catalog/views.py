from django.http import HttpResponse, Http404
import os

# filepath is the full file path of the file on the server
def downloadfile(request, filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r') as fh:
            response = HttpResponse(fh.read())
            response['Content-Disposition'] = 'attachment; filename=' + os.path.basename(filepath)
            return response
    else:
        raise Http404