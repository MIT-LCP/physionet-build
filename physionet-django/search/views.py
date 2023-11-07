import operator
import pdb
import re
from functools import reduce

from django.conf import settings
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.http import Http404
from django.shortcuts import redirect, render, reverse
from django.templatetags.static import static
from physionet.utility import paginate
from project.models import PublishedProject, PublishedTopic
from search import forms


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
    Show all topics

    """
    topics = PublishedTopic.objects.all().order_by('-project_count')

    return render(request, 'search/all_topics.html',
                  {'topics': topics})


def get_content(resource_type, orderby, direction, search_term):
    """
    Helper function to get content shown on a resource listing page
    """
    if 'postgresql' in settings.DATABASES['default']['ENGINE']:
        published_projects = get_content_postgres_full_text_search(resource_type, orderby, direction, search_term)
    else:
        published_projects = get_content_normal_search(resource_type, orderby, direction, search_term)

    return published_projects


def get_content_postgres_full_text_search(resource_type, orderby, direction, search_term):
    from django.contrib.postgres.search import (
        SearchQuery,
        SearchRank,
        SearchVector,
    )

    # Split search term by whitespace or punctuation
    if search_term:
        search_terms = re.split(r'\s*[\;\,\s]\s*', re.escape(search_term))
        search_queries = [SearchQuery(term) for term in search_terms]
        search_query = reduce(operator.and_, search_queries)
        query = Q(resource_type__in=resource_type) & Q(search=search_query)
    else:
        search_query = SearchQuery('')
        query = Q(resource_type__in=resource_type)

    vector = (SearchVector('title', weight='A') + SearchVector('abstract', weight='B')
              + SearchVector('topics__description', weight='C'))

    # Filter projects by latest version and annotate relevance field
    published_projects = PublishedProject.objects.annotate(search=vector).filter(query, is_latest_version=True)

    # get distinct projects with subquery and also include relevance from published_projects
    published_projects = PublishedProject.objects.filter(id__in=published_projects.values('id')).annotate(
        relevance=SearchRank(vector, search_query)).distinct()

    # Sorting
    direction = '-' if direction == 'desc' else ''
    order_string = '{}{}'.format(direction, orderby)

    if orderby == 'relevance':
        published_projects = published_projects.order_by('-relevance', '-publish_datetime')
    else:
        published_projects = published_projects.order_by(order_string, '-relevance')

    return published_projects


def get_content_normal_search(resource_type, orderby, direction, search_term):
    # Word boundary for different database engines
    wb = r'\b'
    if 'postgresql' in settings.DATABASES['default']['ENGINE']:
        wb = r'\y'

    # Build query for resource type and keyword filtering
    if len(search_term) == 0:
        query = Q(resource_type__in=resource_type)
    else:
        search_term = re.split(r'\s*[\;\,\s]\s*', re.escape(search_term))
        query = reduce(operator.or_, (Q(topics__description__iregex=r'{0}{1}{0}'.format(wb,
            item)) for item in search_term))
        query = query | reduce(operator.or_, (Q(abstract__iregex=r'{0}{1}{0}'.format(wb,
            item)) for item in search_term))
        query = query | reduce(operator.or_, (Q(title__iregex=r'{0}{1}{0}'.format(wb,
            item)) for item in search_term))
        query = query & Q(resource_type__in=resource_type)
    published_projects = (PublishedProject.objects
        .filter(query, is_latest_version=True)
        .annotate(relevance=Count('core_project_id'))
        .annotate(has_keys=Value(0, IntegerField()))
    )

    # Relevance
    for t in search_term:
        published_projects = published_projects.annotate(
            has_keys=Case(
                When(title__iregex=r"{0}{1}{0}".format(wb, t), then=Value(3)),
                default=Value(0),
                output_field=IntegerField(),
            )
            + Case(
                When(topics__description__iregex=r"{0}{1}{0}".format(wb, t), then=Value(2)),
                default=Value(0),
                output_field=IntegerField(),
            )
            + Case(
                When(abstract__iregex=r"{0}{1}{0}".format(wb, t), then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).annotate(has_keys=Sum("has_keys"))


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
        else:
            resource_type = list(LABELS.keys())
    elif resource_type is None:
        resource_type = list(LABELS.keys())
        form_type = forms.ProjectTypeForm({'types': resource_type})
    else:
        resource_type = [resource_type]
        form_type = forms.ProjectTypeForm({'types': resource_type})

    # SORT PROJECTS
    orderby, direction = 'relevance', 'desc'
    form_order = forms.ProjectOrderForm()
    if 'orderby' in request.GET:
        form_order = forms.ProjectOrderForm(request.GET)
        if form_order.is_valid():
            orderby, direction = form_order.cleaned_data['orderby'].split('-')

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
                                     search_term=topic)

    # PAGINATION
    projects = paginate(request, published_projects, 10)

    params = request.GET.copy()
    # Remove the page argument from the querystring if it exists
    try:
        params.pop('page')
    except KeyError:
        pass

    querystring = params.urlencode()

    return render(
        request,
        'search/content_index.html',
        {
            'form_order': form_order,
            'projects': projects,
            'form_type': form_type,
            'form_topic': form_topic,
            'querystring': querystring,
        },
    )


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
