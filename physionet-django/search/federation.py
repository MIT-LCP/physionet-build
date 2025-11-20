"""
Federated search functionality across multiple PhysioNet instances.

This module implements:
- Simple keyword-based scoring across metadata fields
- Querying local and federated projects
- Deduplication (preferring local projects)
"""
from django.db.models import Q, Case, When, IntegerField, Value

from project.models import PublishedProject, FederatedProject


def _annotate_score(queryset, keywords, fields_config):
    """
    Annotate queryset with relevance score using DB operations.

    Args:
        queryset: PublishedProject or FederatedProject queryset
        keywords: List of lowercase keywords
        fields_config: Dict mapping field names to score weights

    Returns:
        Queryset annotated with 'search_score' field
    """
    # Start with base score of 0
    score_annotation = Value(0, output_field=IntegerField())

    # Add score contributions for each keyword across all configured fields
    for keyword in keywords:
        for field, weight in fields_config.items():
            score_annotation += Case(
                When(**{f'{field}__icontains': keyword}, then=Value(weight)),
                default=Value(0),
                output_field=IntegerField()
            )

    return queryset.annotate(search_score=score_annotation)


# Field configurations for scoring
LOCAL_FIELDS = {
    'title': 3,
    'abstract': 2,
    'topics__description': 2,
    'short_description': 1,
    'slug': 1,
    'doi': 1,
    'project_home_page': 1,
    'license__name': 1,
    'dua__name': 1,
}

FEDERATED_FIELDS = {
    'title': 3,
    'abstract': 2,
    'slug': 1,
    'source_url': 1,
    'source_site__site_name': 1,
}


def _get_local_projects(resource_type, keywords):
    """
    Get local projects with optional prefiltering.

    Args:
        resource_type: List of resource type IDs to filter by
        keywords: List of lowercase keywords for prefiltering

    Returns:
        QuerySet of PublishedProject instances
    """
    base_query = PublishedProject.objects.filter(
        is_latest_version=True
    ).select_related(
        'core_project', 'license', 'dua', 'resource_type'
    ).prefetch_related('topics')

    # Filter by resource type if provided
    if resource_type:
        base_query = base_query.filter(resource_type__in=resource_type)

    # Prefilter if keywords provided (performance optimization)
    if keywords:
        q_filters = Q()
        for keyword in keywords:
            q_filters |= (
                Q(title__icontains=keyword) |
                Q(abstract__icontains=keyword) |
                Q(short_description__icontains=keyword) |
                Q(slug__icontains=keyword) |
                Q(doi__icontains=keyword) |
                Q(project_home_page__icontains=keyword) |
                Q(topics__description__icontains=keyword)
            )
        base_query = base_query.filter(q_filters).distinct()

    return base_query


def _get_federated_projects(resource_type, keywords):
    """
    Get federated projects with optional prefiltering.

    Args:
        resource_type: List of resource type IDs to filter by
        keywords: List of lowercase keywords for prefiltering

    Returns:
        QuerySet of FederatedProject instances
    """
    base_query = FederatedProject.objects.filter(
        source_site__is_active=True,
        is_stale=False
    ).select_related('source_site')

    # Filter by resource type if provided
    if resource_type:
        base_query = base_query.filter(resource_type__in=resource_type)

    # Prefilter if keywords provided (performance optimization)
    if keywords:
        q_filters = Q()
        for keyword in keywords:
            q_filters |= (
                Q(title__icontains=keyword) |
                Q(abstract__icontains=keyword) |
                Q(slug__icontains=keyword) |
                Q(source_url__icontains=keyword) |
                Q(source_site__site_name__icontains=keyword)
            )
        base_query = base_query.filter(q_filters)

    return base_query


def query_local_projects(resource_type, search_term, orderby='relevance', direction='desc'):
    """
    Query local published projects (legacy compatibility wrapper).

    Args:
        resource_type: List of resource type IDs to filter by
        search_term: Search keywords (space-separated)
        orderby: Field to order by (ignored, kept for compatibility)
        direction: 'asc' or 'desc' (ignored, kept for compatibility)

    Returns:
        QuerySet of PublishedProject instances
    """
    keywords = [k.lower() for k in search_term.strip().split() if k]
    return _get_local_projects(resource_type, keywords)


def query_federated_projects(resource_type, search_term):
    """
    Query federated projects from registered sites (legacy compatibility wrapper).

    Args:
        resource_type: List of resource type IDs to filter by
        search_term: Search keywords (space-separated)

    Returns:
        QuerySet of FederatedProject instances
    """
    keywords = [k.lower() for k in search_term.strip().split() if k]
    return _get_federated_projects(resource_type, keywords)


def get_federated_content(resource_type, search_term, include_federated=True):
    """
    Get all content (local + federated) for search.

    This is the main entry point for federated search.

    Args:
        resource_type: List of resource type IDs to filter by
        search_term: Search keywords (space-separated)
        include_federated: Whether to include federated results

    Returns:
        List of project instances (PublishedProject or FederatedProject),
        sorted by score (descending). Each instance has:
        - search_score: relevance score
        - is_federated: Boolean flag for display badge
    """
    # Parse keywords
    keywords = [k.lower() for k in search_term.strip().split() if k]

    # Collect all projects in a single list
    all_projects = []

    # Get local projects
    local_projects = _get_local_projects(resource_type, keywords)
    if keywords:
        local_projects = _annotate_score(local_projects, keywords, LOCAL_FIELDS)
    else:
        local_projects = local_projects.annotate(search_score=Value(0, output_field=IntegerField()))

    for project in local_projects:
        project.is_federated = False
        all_projects.append(project)

    # Get federated projects if requested
    if include_federated:
        federated_projects = _get_federated_projects(resource_type, keywords)
        if keywords:
            federated_projects = _annotate_score(federated_projects, keywords, FEDERATED_FIELDS)
        else:
            federated_projects = federated_projects.annotate(search_score=Value(0, output_field=IntegerField()))

        for project in federated_projects:
            project.is_federated = True
            all_projects.append(project)

    # Sort all projects by score (descending), then publish_datetime (descending), then title (ascending)
    all_projects.sort(
        key=lambda p: (
            -p.search_score,
            -p.publish_datetime.timestamp() if p.publish_datetime else 0,
            p.title.lower()
        )
    )

    return all_projects
