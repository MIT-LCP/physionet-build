"""Aggregate registered dataset access and project submission metrics."""

import csv
from collections import Counter
from datetime import datetime, time, timedelta

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.http import HttpResponse
from django.utils import timezone

from project.models import AccessLog, ActiveProject, Author, PublishedAuthor, PublishedProject
from user.models import COUNTRIES, CredentialApplication, User


class UsageDateForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))

    def clean(self):
        data = super().clean()
        start, end = data.get('start_date'), data.get('end_date')
        if start and end and start > end:
            raise forms.ValidationError('Start date must be on or before end date.')
        if end and end > timezone.localdate():
            self.add_error('end_date', 'End date cannot be in the future.')
        return data


def _breakdown(users, field, labels):
    total = users.count()
    groups = users.order_by().values(field).annotate(count=Count('pk')).order_by('-count', field)
    counts = Counter()
    for group in groups:
        counts[str(labels.get(group[field], 'Not available'))] += group['count']
    return [
        {'label': label, 'count': count, 'percentage': round(count * 100 / total, 2)}
        for label, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def _demographics(users):
    # One application per user, so repeat applications cannot inflate the counts.
    latest = CredentialApplication.objects.filter(
        user_id=OuterRef('pk'), status=CredentialApplication.Status.ACCEPTED,
    ).order_by('-application_datetime', '-pk')
    return users.annotate(
        credential_id=Subquery(latest.values('pk')[:1]),
        credential_country=Subquery(latest.values('country')[:1]),
        credential_category=Subquery(latest.values('researcher_category')[:1]),
        credential_course=Subquery(latest.values('course_category')[:1]),
    )


def usage_metrics(start_date, end_date):
    """Use inclusive calendar dates in the application's current time zone."""
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    published_type = ContentType.objects.get_for_model(PublishedProject)
    active_type = ContentType.objects.get_for_model(ActiveProject)
    # ProjectType 0 is Database; software and other resource types are not dataset views.
    datasets = PublishedProject.objects.filter(resource_type_id=0)
    logs = AccessLog.objects.filter(
        content_type=published_type, object_id__in=datasets.values('pk'),
        creation_datetime__lt=end, last_access_datetime__gte=start,
    )
    viewers = _demographics(User.objects.filter(pk__in=logs.values('user_id')))
    viewer_count = viewers.count()
    top_datasets = list(
        datasets.filter(logs__pk__in=logs.values('pk')).order_by().values('slug')
        .annotate(count=Count('logs__user', distinct=True)).order_by('-count', 'slug')[:20]
    )
    accessed_datasets = datasets.filter(pk__in=logs.values('object_id')).order_by().values('slug').distinct().count()

    published = PublishedProject.objects.filter(submission_datetime__gte=start, submission_datetime__lt=end)
    # Prefer the published snapshot if the same core/version also has an active row.
    published_version = PublishedProject.objects.filter(core_project_id=OuterRef('core_project_id'),
                                                        version=OuterRef('version'))
    active = ActiveProject.objects.filter(submission_datetime__gte=start, submission_datetime__lt=end).annotate(
        already_published=Exists(published_version),
    ).filter(already_published=False)
    active_authors = Author.objects.filter(
        content_type=active_type, object_id__in=active.values('pk'), is_submitting=True,
    )
    published_authors = PublishedAuthor.objects.filter(project__in=published, is_submitting=True)
    submitters = _demographics(User.objects.filter(
        Q(pk__in=active_authors.values('user_id')) | Q(pk__in=published_authors.values('user_id')),
    ))
    by_resource = Counter()
    for projects in (active, published):
        for row in projects.order_by().values('resource_type__name').annotate(count=Count('pk')):
            by_resource[row['resource_type__name']] += row['count']
    submission_count = sum(by_resource.values())
    missing_submitters = (
        active.exclude(pk__in=active_authors.values('object_id')).count()
        + published.exclude(pk__in=published_authors.values('project_id')).count()
    )

    overview = [
        ('Unique registered dataset viewers', viewer_count),
        ('Datasets accessed (versions combined)', accessed_datasets),
        ('Submitted project versions', submission_count),
        ('Unique submitting authors', submitters.count()),
        ('Viewers with an approved credential application', viewers.filter(credential_id__isnull=False).count()),
        ('Submitters with an approved credential application', submitters.filter(credential_id__isnull=False).count()),
        ('Submitted versions without a recorded submitting author', missing_submitters),
    ]
    countries = dict(COUNTRIES)
    categories = dict(CredentialApplication.RESEARCHER_CATEGORIES)
    return [
        {'title': 'Overview', 'description': '',
         'rows': [{'label': label, 'count': count, 'percentage': None} for label, count in overview]},
        {'title': 'Most accessed datasets',
         'description': ('Top 20 by unique registered viewers, combining all versions. '
                         'A person may view multiple datasets.'),
         'rows': [{'label': row['slug'], 'count': row['count'],
                   'percentage': round(row['count'] * 100 / viewer_count, 2)} for row in top_datasets]},
        {'title': 'Dataset viewers by country', 'description': 'Percentage of all unique registered dataset viewers.',
         'rows': _breakdown(viewers, 'credential_country', countries)},
        {'title': 'Dataset viewers by researcher category',
         'description': 'Percentage of all unique registered dataset viewers.',
         'rows': _breakdown(viewers, 'credential_category', categories)},
        {'title': 'Declared course use',
         'description': ('Self-reported during credentialing. This does not establish how any particular '
                         'dataset was used. Percentage of all unique registered dataset viewers.'),
         'rows': _breakdown(viewers, 'credential_course', dict(CredentialApplication.COURSE_CATEGORIES))},
        {'title': 'Submissions by resource type',
         'description': ('Submitted versions, including active, archived, and published projects. '
                         'Revisions are not counted again.'),
         'rows': [{'label': label, 'count': count, 'percentage': round(count * 100 / submission_count, 2)}
                  for label, count in sorted(by_resource.items(), key=lambda pair: (-pair[1], pair[0]))]},
        {'title': 'Submitting authors by country',
         'description': 'Percentage of unique submitting authors, not all coauthors.',
         'rows': _breakdown(submitters, 'credential_country', countries)},
        {'title': 'Submitting authors by researcher category',
         'description': 'Percentage of unique submitting authors, not all coauthors.',
         'rows': _breakdown(submitters, 'credential_category', categories)},
    ]


def usage_csv(sections, start_date, end_date):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="usage-stats.csv"'
    writer = csv.writer(response)
    writer.writerow(['Start date', 'End date', 'Section', 'Metric', 'Count', 'Percentage'])
    for section in sections:
        for row in section['rows']:
            writer.writerow([start_date, end_date, section['title'], row['label'], row['count'], row['percentage']])
    return response
