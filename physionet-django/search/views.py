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
            return redirect('topic_search', topic=request.GET['description'])
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
    topics = PublishedTopic.objects.all().order_by('project_count')

    return render(request, 'search/all_topics.html', {'topics':topics})
