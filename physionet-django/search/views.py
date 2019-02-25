import pdb

from django.shortcuts import render, redirect, reverse

from . import forms
from project.models import PublishedProject, PublishedTopic


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


def get_content(resource_type, orderby, direction):
    """
    Helper function to get content shown on a resource listing page
    """
    if resource_type is None:
        published_projects = PublishedProject.objects.all()
    else:
        published_projects = PublishedProject.objects.filter(
            resource_type=resource_type)

    direction = '-' if direction == 'desc' else ''

    order_string = '{}{}'.format(direction, orderby)
    published_projects = published_projects.order_by(order_string)

    authors = [p.authors.all() for p in published_projects]
    topics = [p.topics.all() for p in published_projects]
    projects_authors_topics = zip(published_projects, authors, topics)

    return projects_authors_topics


def content_index(request):
    """
    List of all published resources
    """
    orderby, direction = 'publish_datetime', 'desc'
    form = forms.ProjectOrderForm()

    if 'orderby' in request.GET or 'direction' in request.GET:
        form = forms.ProjectOrderForm(request.GET)
        if form.is_valid():
            orderby, direction = [form.cleaned_data[item] for item in ['orderby', 'direction']]
        projects_authors_topics = get_content(resource_type=None,
            orderby=orderby, direction=direction)
    else:
        projects_authors_topics = get_content(resource_type=None,
            orderby=orderby, direction=direction)

    return render(request, 'search/content_index.html', {'form':form,
        'projects_authors_topics':projects_authors_topics})


def database_index(request):
    """
    List of published databases
    """
    orderby, direction = 'publish_datetime', 'desc'
    form = forms.ProjectOrderForm()

    if 'orderby' in request.GET or 'direction' in request.GET:
        form = forms.ProjectOrderForm(request.GET)
        if form.is_valid():
            orderby, direction = [form.cleaned_data[item] for item in ['orderby', 'direction']]
        projects_authors_topics = get_content(resource_type=0,
            orderby=orderby, direction=direction)
    else:
        projects_authors_topics = get_content(resource_type=0,
            orderby=orderby, direction=direction)

    return render(request, 'search/database_index.html', {'form':form,
        'projects_authors_topics':projects_authors_topics})


def software_index(request):
    """
    List of published software projects
    """
    orderby, direction = 'publish_datetime', 'desc'
    form = forms.ProjectOrderForm()

    if 'orderby' in request.GET or 'direction' in request.GET:
        form = forms.ProjectOrderForm(request.GET)
        if form.is_valid():
            orderby, direction = [form.cleaned_data[item] for item in ['orderby', 'direction']]
        projects_authors_topics = get_content(resource_type=1,
            orderby=orderby, direction=direction)
    else:
        projects_authors_topics = get_content(resource_type=1,
            orderby=orderby, direction=direction)

    return render(request, 'search/software_index.html', {'form':form,
        'projects_authors_topics':projects_authors_topics})
