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


def topic_search(request, topic=''):
    """
    Search published projects by topic keyword

    Search with form submission or direct url
    """
    # Redirect to show url if successful search
    if 'search' in request.GET:
        form = forms.TopicSearchForm(request.GET)
        if form.is_valid():
            return redirect('topic_search', topic=form.cleaned_data['description'].lower())
        else:
            projects = None
            valid_search = False
    else:
        projects = PublishedProject.objects.filter(topics__description=topic) if topic else None
        form = forms.TopicSearchForm(initial={'description':topic})
        valid_search = True if topic else False

    return render(request, 'search/topic_search.html', {'topic':topic,
        'projects':projects, 'form':form, 'valid_search':valid_search})


def all_topics(request):
    """
    Show all topics contained in PhysioNet

    """
    topics = PublishedTopic.objects.all().order_by('-project_count')

    return render(request, 'search/all_topics.html', {'topics':topics})


def get_content(resource_type=None, order_by=None, direction=None):
    """
    Helper function to get content shown on a resource listing page
    """
    if resource_type is None:
        published_projects = PublishedProject.objects.all().order_by(
            '-publish_datetime')
    else:
        published_projects = PublishedProject.objects.filter(
            resource_type=resource_type).order_by('-publish_datetime')

    authors = [p.authors.all() for p in published_projects]
    topics = [p.topics.all() for p in published_projects]
    projects_authors_topics = zip(published_projects, authors, topics)

    return projects_authors_topics


def content_index(request):
    """
    List of all published resources
    """
    projects_authors_topics = get_content()
    return render(request, 'search/content_index.html', {'content_name':'Content',
        'projects_authors_topics':projects_authors_topics})


def database_index(request):
    """
    List of published databases
    """
    if 'order_by' in request.GET:
        form = forms.ProjectOrderForm(request.GET)
        if form.is_valid():
            projects_authors_topics = get_content(resource_type=0)

    else:
        projects_authors_topics = get_content(resource_type=0)

    return render(request, 'search/database_index.html', {'content_name':'Database',
        'projects_authors_topics':projects_authors_topics})


def software_index(request):
    """
    List of published software projects
    """
    projects_authors_topics = get_content(resource_type=1)
    return render(request, 'search/software_index.html', {'content_name':'Software',
        'projects_authors_topics':projects_authors_topics})
