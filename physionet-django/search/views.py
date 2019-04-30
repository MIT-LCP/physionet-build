import pdb
import re

from django.contrib.staticfiles.templatetags.staticfiles import static
from django.shortcuts import render, redirect, reverse

from . import forms
from project.models import PublishedProject, PublishedTopic

import operator
from functools import reduce
from django.db.models import Q, Count, Case, When, Value, IntegerField, Sum

from django.core.paginator import Paginator
from django.conf import settings
from django.http import Http404


def topic_search(request):
    """
    Search published projects by topic keyword

    Search with form submission or direct url
    """
    topic, valid_search, projects = '', False, None
    # If we get a form submission, redirect to generate the querystring
    # in the url
    if 'topic' in request.GET:
        form = forms.TopicSearchForm(request.GET)
        if form.is_valid():
            topic = form.cleaned_data['topic']
            valid_search = True
        projects = PublishedProject.objects.filter(topics__description=topic)
    else:
        form = forms.TopicSearchForm()

    return render(request, 'search/topic_search.html',
                  {'topic': topic,
                   'projects': projects,
                   'form': form,
                   'valid_search': valid_search})


def all_topics(request):
    """
    Show all topics contained in PhysioNet

    """
    topics = PublishedTopic.objects.all().order_by('-project_count')

    return render(request, 'search/all_topics.html',
                  {'topics': topics})


def get_content(resource_type, orderby, direction, topic):
    """
    Helper function to get content shown on a resource listing page
    """

    # Word boundary for different database engines
    wb = r'\b'
    if 'postgresql' in settings.DATABASES['default']['ENGINE']:
        wb = r'\y'

    # Build query for resource type and keyword filtering
    if len(topic) == 0:
        query = Q(resource_type__in=resource_type)
    else:
        topic = re.split(r"\W", topic)
        query = reduce(operator.or_, (Q(topics__description__iregex=r'{0}{1}{0}'.format(wb,
            item)) for item in topic))
        query = query | reduce(operator.or_, (Q(abstract__iregex=r'{0}{1}{0}'.format(wb,
            item)) for item in topic))
        query = query | reduce(operator.or_, (Q(title__iregex=r'{0}{1}{0}'.format(wb,
            item)) for item in topic))
        query = query & Q(resource_type__in=resource_type)
    published_projects = (PublishedProject.objects
        .filter(query, is_latest_version=True)
        .annotate(relevance=Count('core_project_id'))
        .annotate(has_keys=Value(0, IntegerField()))
    )

    # Relevance
    for t in topic:
        published_projects = (published_projects.annotate(has_keys=Case(
                When(topics__description__iregex=r'{0}{1}{0}'.format(wb, t),
                     then=Value(3)),
                When(title__iregex=r'{0}{1}{0}'.format(wb, t),
                     then=Value(2)),
                When(abstract__iregex=r'{0}{1}{0}'.format(wb, t),
                     then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            )).annotate(has_keys=Sum('has_keys'))
        )

    # Sorting
    direction = '-' if direction == 'desc' else ''
    order_string = '{}{}'.format(direction, orderby)
    if orderby == 'relevance':
        published_projects = published_projects.order_by(direction+'has_keys',
            order_string, '-publish_datetime')
    else:
        published_projects = published_projects.order_by(order_string)

    return published_projects


def content_index(request, resource_type=None):
    """
    List of all published resources
    """
    LABELS = {0: ['Database', 'databases'],
              1: ['Software', 'softwares'],
              2: ['Challenge', 'challenges'],
              3: ['Model', 'models'],
              }

    # PROJECT TYPE FILTER
    form_type = forms.ProjectTypeForm()
    if 'types' in request.GET:
        form_type = forms.ProjectTypeForm(request.GET)
        if form_type.is_valid():
            resource_type = [int(t) for t in form_type.cleaned_data['types']]
    elif resource_type is None:
        resource_type = list(LABELS.keys())
        form_type = forms.ProjectTypeForm({'types': resource_type})
    else:
        resource_type = [resource_type]
        form_type = forms.ProjectTypeForm({'types': resource_type})

    # SORT PROJECTS
    orderby, direction = 'publish_datetime', 'desc'
    form_order = forms.ProjectOrderForm()
    if 'orderby' in request.GET or 'direction' in request.GET:
        form_order = forms.ProjectOrderForm(request.GET)
        if form_order.is_valid():
            orderby, direction = [form_order.cleaned_data[item] for item in ['orderby', 'direction']]

    # TOPIC SEARCH
    topic = ''
    if 'topic' in request.GET:
        form_topic = forms.TopicSearchForm(request.GET)
        if form_topic.is_valid():
            topic = form_topic.cleaned_data['topic']
    else:
        form_topic = forms.TopicSearchForm()

    # BUILD
    published_projects = get_content(resource_type=resource_type,
                                     orderby=orderby,
                                     direction=direction,
                                     topic=topic)

    # PAGINATION
    page = request.GET.get('page', 1)
    paginator = Paginator(published_projects, 10)
    try:
        projects = paginator.page(page)
    except:
        projects = paginator.page(1)

    querystring = re.sub(r'\&*page=\d*', '', request.GET.urlencode())
    if querystring != '':
        querystring += '&'

    return render(request, 'search/content_index.html',
                  {'form_order': form_order,
                   'projects': projects,
                   'form_type': form_type,
                   'form_topic': form_topic,
                   'querystring': querystring})


def database_index(request):
    """
    List of published databases
    """
    return content_index(request, resource_type=0)


def software_index(request):
    """
    List of published software
    """
    return content_index(request, resource_type=1)


def challenge_index(request):
    """
    List of published challenges
    """
    return content_index(request, resource_type=2)


def model_index(request):
    """
    List of published models
    """
    return content_index(request, resource_type=3)


def charts(request):
    """
    Chart statistics about published projects
    """
    resource_type = None

    if ('resource_type' in request.GET and
            request.GET['resource_type'] in ['0', '1', '2', '3']):
        resource_type = int(request.GET['resource_type'])

    LABELS = {None: ['Content', 'Projects'],
              0: ['Database', 'Databases'],
              1: ['Software', 'Software Projects'],
              2: ['Challenge', 'Challenges'],
              3: ['Model', 'Models']}

    main_label, plural_label = LABELS[resource_type]
    return render(request, 'search/charts.html', {
                           'resource_type': resource_type,
                           'main_label': main_label,
                           'plural_label': plural_label})


def physiobank(request):
    """Redirect"""
    return redirect('database_index')


def physiotools(request):
    """Redirect"""
    return redirect('software_index')

  
def wfdbcal(request):
    return redirect(static('wfdbcal'))


def redirect_latest_if_project_exists(project_slug):
    project = PublishedProject.objects.filter(slug=project_slug)
    if project:
        return redirect('published_project_latest', project_slug=project_slug)
    else:
        raise Http404()


def redirect_project(request, project_slug):
    return redirect_latest_if_project_exists(project_slug)


def redirect_challenge_project(request, year):
    return redirect_latest_if_project_exists('challenge-{}'.format(year))
