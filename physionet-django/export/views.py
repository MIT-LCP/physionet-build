from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from .serializers import PublishedProjectSerializer
from project.models import PublishedProject
from project import utility


def database_list(request):
    """
    List all published databases
    """
    projects = PublishedProject.objects.filter(resource_type=0).order_by(
        'publish_datetime')
    serializer = PublishedProjectSerializer(projects, many=True)
    return JsonResponse(serializer.data, safe=False)


def software_list(request):
    """
    List all published software projects
    """
    projects = PublishedProject.objects.filter(resource_type=1).order_by(
        'publish_datetime')
    serializer = PublishedProjectSerializer(projects, many=True)
    return JsonResponse(serializer.data, safe=False)


def database_stats_list(request):
    """
    List cumulative stats about projects published.
    The request may specify the desired resource type
    """
    # Get the desired resource type
    if 'resource_type' in request.GET and request.GET['resource_type'] in ['0', '1']:
        resource_type = int(request.GET['resource_type'])
    # Default database
    else:
        resource_type = 0

    projects = PublishedProject.objects.filter(resource_type=resource_type).order_by(
        'publish_datetime')
    data = []
    for year in range(projects[0].publish_datetime.year, timezone.now().year):
        y_projects = projects.filter(publish_datetime__year=year)
        data.append({"year":year, "num_projects":y_projects.count(),
            "storage_size":sum(p.main_storage_size // 1024**3 for p in y_projects)})

    return JsonResponse(data, safe=False)
