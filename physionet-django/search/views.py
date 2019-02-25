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
    if 'search' in request.GET:
        return redirect('{}?t={}'.format(reverse('topic_search'), request.GET['t']))
    # A search via direct url entry
    elif 't' in request.GET:
        form = forms.TopicSearchForm(request.GET)
        if form.is_valid():
            topic = form.cleaned_data['t']
            projects = PublishedProject.objects.filter(topics__description=topic)
            valid_search = True
    else:
        form = forms.TopicSearchForm()

    return render(request, 'search/topic_search.html', {'topic':topic,
        'projects':projects, 'form':form, 'valid_search':valid_search})


def all_topics(request):
    """
    Show all topics contained in PhysioNet

    """
    topics = PublishedTopic.objects.all().orderby('-project_count')

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
    pdb.set_trace()
    published_projects = published_projects.order_by(order_string)

    authors = [p.authors.all() for p in published_projects]
    topics = [p.topics.all() for p in published_projects]
    projects_authors_topics = zip(published_projects, authors, topics)

    return projects_authors_topics


def content_index(request):
    """
    List of all published resources
    """
    projects_authors_topics = get_content()
    return render(request, 'search/content_index.html', {
        'projects_authors_topics':projects_authors_topics})


def database_index(request):
    """
    List of published databases
    """
    orderby, direction = 'publish_datetime', 'asc'
    form = forms.ProjectOrderForm()

    # If we get a form submission, redirect to generate the querystring
    # in the url
    # if 'search' in request.GET:
    #     if 'orderby' in request.GET:
    #         orderby = request.GET['orderby']
    #     if 'direction' in request.GET:
    #         direction = request.GET['direction']
    #     return redirect('{}?orderby={}&direction={}'.format(reverse('database_index'), orderby, direction))
    # A search via direct url entry
    if 'order_by' in request.GET or 'direction' in request.GET:
        form = forms.ProjectOrderForm(request.GET)
        if form.is_valid():
            orderby, direction = [form.cleaned_data[item] for item in ['orderby', 'direction']]
        pdb.set_trace()
        projects_authors_topics = get_content(resource_type=0,
            orderby=orderby, direction=direction)
        pdb.set_trace()
    else:
        projects_authors_topics = get_content(resource_type=0,
            orderby=orderby, direction=direction)

    return render(request, 'search/database_index.html', {'form':form,
        'projects_authors_topics':projects_authors_topics})


def software_index(request):
    """
    List of published software projects
    """
    projects_authors_topics = get_content(resource_type=1)
    return render(request, 'search/software_index.html', {
        'projects_authors_topics':projects_authors_topics})
