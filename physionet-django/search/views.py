import pdb
import re

from django.shortcuts import render, redirect, reverse

from . import forms
from project.models import PublishedProject, PublishedTopic

import operator
from functools import reduce
from django.db.models import Q, Count


def google_custom_search(request):
    """
    Page for performing google custom search on the site
    """
    return render(request, 'search/google_custom_search.html')


def redirect_google_custom_search(request):
    """
    Used to redirect queries from the navbar search to the main google
    search page

    """
    return redirect(reverse('google_custom_search') + '?q={}'.format(request.GET['query']))


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

    return render(request, 'search/topic_search.html', {'topic':topic,
        'projects':projects, 'form':form, 'valid_search':valid_search})


def all_topics(request):
    """
    Show all topics contained in PhysioNet

    """
    topics = PublishedTopic.objects.all().order_by('-project_count')

    return render(request, 'search/all_topics.html', {'topics':topics})


def get_content(resource_type, orderby, direction, topic):
    """
    Helper function to get content shown on a resource listing page
    """
    if resource_type is None:
        published_projects = PublishedProject.objects.all().annotate(relevance=Count('core_project_id'))
    elif type(resource_type) != list:       
        resource_type = [resource_type]

    if topic == '' or len(topic) == 0:
        published_projects = PublishedProject.objects.filter(
            resource_type__in=resource_type).annotate(relevance=Count('core_project_id'))
    else:
        topic = re.split(r"\W",topic);
        query = reduce(operator.or_, (Q(topics__description__iregex = r'{0}'.format(item)) for item in topic))
        query = query | reduce(operator.or_, (Q(abstract__iregex = r'\b{0}\b'.format(item)) for item in topic))
        query = query | reduce(operator.or_, (Q(title__iregex = r'\b{0}\b'.format(item)) for item in topic))
        query = query & Q(resource_type__in=resource_type)
        published_projects = PublishedProject.objects.filter(query).annotate(relevance=Count('core_project_id'))

    direction = '-' if direction == 'desc' else ''

    order_string = '{}{}'.format(direction, orderby)
    published_projects = published_projects.order_by(order_string)

    authors = [p.authors.all() for p in published_projects]
    topics = [p.topics.all() for p in published_projects]
    projects_authors_topics = zip(published_projects, authors, topics)
    nprojects = len(published_projects)

    return projects_authors_topics, nprojects


def content_index(request, resource_type=None):
    """
    List of all published resources
    """
    LABELS = {0:['Database', 'databases'],
        1:['Software', 'softwares'], 2:['Challenge', 'challenges']}


    # PROJECT TYPE FILTER
    form_type = forms.ProjectTypeForm()
    if 'types' in request.GET:
        form_type = forms.ProjectTypeForm(request.GET)
        if form_type.is_valid():
            resource_type = [int(t) for t in form_type.cleaned_data['types']]
    elif resource_type is None:
        resource_type = list(LABELS.keys())
        form_type = forms.ProjectTypeForm({'types':resource_type})
    else:
        resource_type = [resource_type]
        form_type = forms.ProjectTypeForm({'types':resource_type})
    main_label = ', '.join([LABELS[r][0] for r in resource_type])
    plural_label = ', '.join([LABELS[r][1] for r in resource_type])

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
    projects_authors_topics, nprojects = get_content(resource_type=resource_type,
            orderby=orderby, direction=direction, topic=topic)
    

    return render(request, 'search/content_index.html', {'form_order':form_order,
        'projects_authors_topics':projects_authors_topics,
        'main_label':main_label, 'plural_label':plural_label,
        'form_type':form_type, 'form_topic':form_topic,'nprojects':nprojects})


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

def charts(request):
    """
    Chart statistics about published projects
    """
    resource_type = None

    if 'resource_type' in request.GET and request.GET['resource_type'] in ['0', '1']:
        resource_type = int(request.GET['resource_type'])

    LABELS = {None:['Content', 'Projects'], 0:['Database', 'Databases'],
        1:['Software', 'Software Projects'], 2:['Challenge', 'Challenges']}

    main_label, plural_label = LABELS[resource_type]
    return render(request, 'search/charts.html', {
        'resource_type':resource_type,
        'main_label':main_label, 'plural_label':plural_label})
