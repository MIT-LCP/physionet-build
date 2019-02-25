from django.http import JsonResponse
from django.shortcuts import render

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

    projects = PublishedProject.objects.filter(resource_type=0).order_by('publish_datetime')



    data = {
        'published':{
            '2010':5,
            '2011':8,
            '2012':9
        },
        'storage':{
            '2010':10,
            '2011':11,
            '2012':12
        }
    }

    data = {'2010':'1', '2011':'2'}
    return JsonResponse(data, safe=False)

