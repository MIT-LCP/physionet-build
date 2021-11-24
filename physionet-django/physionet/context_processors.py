from project.models import AccessPolicy


def access_policy(request):
    return {'AccessPolicy': AccessPolicy}
