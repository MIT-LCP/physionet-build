import threading

_request_local = threading.local()

def get_current_request():
    """Retrieve the current request from thread-local storage."""
    return getattr(_request_local, 'request', None)

class CurrentRequestMiddleware:
    """Middleware to store the current request in thread-local storage."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _request_local.request = request
        response = self.get_response(request)
        return response
