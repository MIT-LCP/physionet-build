from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from .serializers import PublishedProjectSerializer
from project.models import PublishedProject


def database_list(request):
    """
    List all published databases
    """
    projects = PublishedProject.objects.filter(resource_type=0).order_by('publish_datetime')
    serializer = PublishedProjectSerializer(projects, many=True)
    return JsonResponse(serializer.data, safe=False)


def software_list(request):
    """
    List all published software projects
    """
    projects = PublishedProject.objects.filter(resource_type=1).order_by('publish_datetime')
    serializer = PublishedProjectSerializer(projects, many=True)
    return JsonResponse(serializer.data, safe=False)


def database_stats_list(request):
    """
    List cumulative stats about database published
    """
    data = []
    projects = PublishedProject.objects.filter(resource_type=0).order_by('publish_datetime')

    for year in range(projects[0].publish_datetime.year, timezone.now().year):
        y_projects = projects.filter(publish_datetime__year=year)
        data.append({"Year":year, "Projects":y_projects.count(), "Size":20})


    # data = [
    #     {
    #         "Year":2010,
    #         "Projects":10,
    #         "Storage":40
    #     },
    #     {
    #         "Year":2011,
    #         "Projects":11,
    #         "Storage":45
    #     },
    #     {
    #         "Year":2012,
    #         "Projects":12,
    #         "Storage":50
    #     }
    # ]

    return JsonResponse(data, safe=False)

