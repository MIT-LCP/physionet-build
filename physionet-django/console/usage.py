"""Aggregate console usage metrics."""

import csv
from collections import Counter
from datetime import datetime, time, timedelta

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import BooleanField, Case, Count, Max, Min, OuterRef, Q, Subquery, Value, When
from django.http import HttpResponse
from django.utils import timezone

from project.models import AccessLog, ActiveProject, Author, DataAccessRequest, PublishedAuthor, PublishedProject
from user.models import COUNTRIES, CredentialApplication, User


def dataset_logs(start_date=None, end_date=None):
    """Access logs of published datasets, limited to sessions started within the dates when given."""
    # ProjectType 0 is Database; software and other resource types are not dataset views.
    logs = AccessLog.objects.filter(
        content_type=ContentType.objects.get_for_model(PublishedProject),
        object_id__in=PublishedProject.objects.filter(resource_type_id=0).values('pk'),
    )
    if start_date and end_date:
        logs = logs.filter(
            creation_datetime__gte=timezone.make_aware(datetime.combine(start_date, time.min)),
            creation_datetime__lt=timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min)),
        )
    return logs


def usage_record_dates():
    """Cache dataset access-log bounds for five minutes, independently of filters."""
    key = 'console:usage:record-dates:v1'
    bounds = cache.get(key)
    if bounds is None:
        bounds = dataset_logs().aggregate(first=Min('creation_datetime'), last=Max('creation_datetime'))
        cache.set(key, bounds, 300)
    return {name: timezone.localdate(value) if value else None for name, value in bounds.items()}


class UsageDateForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))

    def __init__(self, *args, first_record_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.first_record_date = first_record_date
        for field in self.fields.values():
            field.widget.attrs['max'] = timezone.localdate().isoformat()
            if first_record_date:
                field.widget.attrs['min'] = first_record_date.isoformat()

    def clean(self):
        data = super().clean()
        start, end = data.get('start_date'), data.get('end_date')
        if start and self.first_record_date and start < self.first_record_date:
            self.add_error('start_date', 'Start date cannot be before the first available record '
                           f'({self.first_record_date.isoformat()}).')
        if start and end and start > end:
            raise forms.ValidationError('Start date must be on or before end date.')
        if end and end > timezone.localdate():
            self.add_error('end_date', 'End date cannot be in the future.')
        return data


def _viewer_demographic(users, field, labels, title, population='viewers'):
    """Distinguish unavailable fields from the absence of an approved application."""
    groups = users.annotate(has_approved=Case(
        When(credential_id__isnull=False, then=Value(True)), default=Value(False), output_field=BooleanField(),
    )).order_by().values('has_approved', field).annotate(count=Count('pk'))
    counts = Counter()
    available = set()
    for group in groups:
        if not group['has_approved']:
            label = 'No approved credential application'
        elif group[field] not in labels:
            label = 'Information missing or unrecognized'
        else:
            label = str(labels[group[field]])
            available.add(label)
        counts[label] += group['count']
    total = sum(counts.values())
    known = sum(counts[label] for label in available)
    definitions = {
        'credential_country': 'Countries are institutional countries, not nationalities or inferred locations.',
        'credential_category': 'Researcher categories are self-reported during credentialing.',
        'credential_course': 'Course use is self-reported during credentialing and does not establish how '
                             'any particular dataset was used.',
    }
    return {
        'key': field.removeprefix('credential_'), 'title': title, 'population': population,
        'coverage_count': known, 'coverage_total': total,
        'coverage_population': {'viewers': 'registered viewers', 'approved users': 'approved users',
                                'submitting authors': 'submitting authors'}[population],
        'coverage_percentage': round(100 * known / total, 2) if total else None,
        'description': 'Uses the latest currently approved credential application, not a historical snapshot. '
                       'No approved application is separate from missing or unrecognized information on an approved '
                       f'application. All {population} (%) uses every unique person in this population. '
                       'With information (%) uses only people with a recognized value for this field, '
                       'excluding both unavailable groups. '
                       + definitions[field],
        'rows': [
            {'label': label, 'count': count, 'percentage': round(100 * count / total, 2),
             'information_available': label in available,
             'available_percentage': round(100 * count / known, 2) if label in available else None}
            for label, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
    }


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
        credential_organization=Subquery(latest.values('organization_name')[:1]),
    )


def _institution_count(users):
    # Names are self-reported: normalize spelling format, not institutional identity.
    return len({
        ' '.join(name.split()).casefold()
        for name in users.values_list('credential_organization', flat=True)
        if name and name.strip()
    })


def _account_age(users, start_date, end_date):
    counts = [
        ('New accounts (created during selected dates)',
         users.filter(join_date__gte=start_date, join_date__lte=end_date).count()),
        ('Existing accounts (created before selected dates)', users.filter(join_date__lt=start_date).count()),
    ]
    # Imported or inconsistent historical records must not be labeled as new accounts.
    unavailable = users.filter(join_date__gt=end_date).count()
    if unavailable:
        counts.append(('Not available (account created after selected dates)', unavailable))
    total = sum(count for _, count in counts)
    return [{'label': label, 'count': count, 'percentage': round(count * 100 / total, 2)}
            for label, count in counts] if total else []


def usage_metrics(start_date, end_date):
    datasets = PublishedProject.objects.filter(resource_type_id=0)
    logs = dataset_logs(start_date, end_date)
    viewers = _demographics(User.objects.filter(pk__in=logs.values('user_id')))
    viewer_count = viewers.count()
    top_datasets = list(
        datasets.filter(logs__pk__in=logs.values('pk')).order_by().values('slug')
        .annotate(count=Count('logs__user', distinct=True)).order_by('-count', 'slug')[:10]
    )
    accessed_datasets = datasets.filter(pk__in=logs.values('object_id')).order_by().values('slug').distinct().count()

    version_views = (
        datasets.filter(logs__pk__in=logs.values('pk')).order_by().values('slug', 'version')
        .annotate(count=Count('logs__user', distinct=True)).order_by('-count', 'slug', 'version')
    )

    overview = [
        ('Unique registered dataset viewers', viewer_count),
        ('Distinct declared institution names among viewers', _institution_count(viewers)),
        ('Datasets accessed (versions combined)', accessed_datasets),
        ('Viewers with an approved credential application', viewers.filter(credential_id__isnull=False).count()),
    ]
    countries = dict(COUNTRIES)
    categories = dict(CredentialApplication.RESEARCHER_CATEGORIES)
    return [
        {'key': 'overview', 'title': 'Overview', 'description': (
            'All cards summarize the entire selected period, not the sum of monthly values. '
            'Each viewer is counted once, even if they appear in several months. Datasets combine all versions; '
            'institutions count distinct self-reported names, ignoring case and extra spaces. Spelling variants '
            'and abbreviations may still count separately. Approved viewers are a subset of the same unique '
            'viewers, using their latest currently approved credential application. '
            'Cards, tables and monthly charts all count sessions that started within the selected dates.'),
         'rows': [{'label': label, 'count': count,
                   'percentage': round(100 * count / viewer_count, 2)
                   if label == 'Viewers with an approved credential application' and viewer_count else None}
                  for label, count in overview]},
        {'key': 'top_datasets', 'title': 'Most accessed datasets',
         'description': ('Top 10 by unique registered viewers, combining all versions. '
                         'A person may view multiple datasets.'),
         'rows': [{'label': row['slug'], 'count': row['count'],
                   'percentage': round(row['count'] * 100 / viewer_count, 2)} for row in top_datasets]},
        _viewer_demographic(viewers, 'credential_country', countries, 'Dataset viewers by country'),
        _viewer_demographic(viewers, 'credential_category', categories, 'Dataset viewers by researcher category'),
        {**_viewer_demographic(
            viewers, 'credential_course', dict(CredentialApplication.COURSE_CATEGORIES), 'Declared course use'),
         'csv_only': True},
        {'key': 'versions', 'title': 'Registered viewers by dataset version',
         'description': 'Unique registered file-access viewers per version. A person may appear in multiple versions.',
         'rows': [{'label': f"{row['slug']} / {row['version']}", 'count': row['count'], 'percentage': None}
                  for row in version_views]},
        {'key': 'account_age', 'title': 'Dataset viewers by account age',
         'description': 'New means the account was created during the selected dates, not first use of a dataset.',
         'rows': _account_age(viewers, start_date, end_date)},
    ]


def access_metrics(start_date, end_date):
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    datasets = PublishedProject.objects.filter(resource_type_id=0)
    requests = DataAccessRequest.objects.filter(
        project__in=datasets, request_datetime__gte=start, request_datetime__lt=end,
    )
    # Revoked requests retain their original approval decision timestamp.
    approvals = DataAccessRequest.objects.filter(
        project__in=datasets, decision_datetime__gte=start, decision_datetime__lt=end,
        status__in=(DataAccessRequest.ACCEPT_REQUEST_VALUE, DataAccessRequest.REVOKED_VALUE),
    )
    approved_users = _demographics(User.objects.filter(pk__in=approvals.values('requester_id')))
    rejections = DataAccessRequest.objects.filter(
        project__in=datasets, decision_datetime__gte=start, decision_datetime__lt=end,
        status=DataAccessRequest.REJECT_REQUEST_VALUE,
    )
    overview = [
        ('Dataset access requests submitted', requests.count()),
        ('Unique dataset access requesters', requests.values('requester_id').distinct().count()),
        ('Unique users approved for dataset access during selected dates', approved_users.count()),
        ('Dataset access approvals recorded', approvals.count()),
        ('Dataset access rejections recorded', rejections.count()),
        ('Distinct declared institution names among approved users', _institution_count(approved_users)),
    ]
    countries = dict(COUNTRIES)
    categories = dict(CredentialApplication.RESEARCHER_CATEGORIES)
    return [
        {'key': 'overview', 'title': 'Overview', 'description': '',
         'rows': [{'label': label, 'count': count,
                   'percentage': None}
                  for label, count in overview]},
        _viewer_demographic(approved_users, 'credential_country', countries,
                            'Approved dataset users by country', population='approved users'),
        _viewer_demographic(approved_users, 'credential_category', categories,
                            'Approved dataset users by researcher category', population='approved users'),
        {'key': 'account_age', 'title': 'Approved dataset users by account age',
         'description': ('Users approved during the selected dates. New means the account was created during '
                         'those dates, not necessarily when access was requested.'),
         'rows': _account_age(approved_users, start_date, end_date)},
    ]


def submissions_metrics(start_date, end_date):
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    active_type = ContentType.objects.get_for_model(ActiveProject)
    published = PublishedProject.objects.filter(submission_datetime__gte=start, submission_datetime__lt=end)
    active = ActiveProject.objects.filter(submission_datetime__gte=start, submission_datetime__lt=end)
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
        ('Distinct declared institution names among submitting authors', _institution_count(submitters)),
        ('Project versions first submitted', submission_count),
        ('Unique submitting authors', submitters.count()),
        ('Submitters with an approved credential application', submitters.filter(credential_id__isnull=False).count()),
        ('Submitted versions without a recorded submitting author', missing_submitters),
    ]
    countries = dict(COUNTRIES)
    categories = dict(CredentialApplication.RESEARCHER_CATEGORIES)
    return [
        {'key': 'overview', 'title': 'Overview', 'description': '',
         'rows': [{'label': label, 'count': count,
                   'percentage': None}
                  for label, count in overview]},
        {'key': 'account_age', 'title': 'Submitting authors by account age',
         'description': 'New means the account was created during the selected dates.',
         'rows': _account_age(submitters, start_date, end_date)},
        {'key': 'resource_type', 'title': 'Submissions by resource type',
         'description': ('Submitted versions, including active, archived, and published projects. '
                         'Revisions are not counted again.'),
         'rows': [{'label': label, 'count': count, 'percentage': round(count * 100 / submission_count, 2)}
                  for label, count in sorted(by_resource.items(), key=lambda pair: (-pair[1], pair[0]))]},
        _viewer_demographic(submitters, 'credential_country', countries,
                            'Submitting authors by country', population='submitting authors'),
        _viewer_demographic(submitters, 'credential_category', categories,
                            'Submitting authors by researcher category', population='submitting authors'),
    ]


def usage_csv(sections, start_date, end_date):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="usage-stats.csv"'
    writer = csv.writer(response)
    demographics = any('coverage_total' in section for section in sections)
    headers = ['Start date', 'End date', 'Section', 'Metric', 'Count', 'Percentage', 'Row type']
    if demographics:
        population = next(section['population'] for section in sections if 'population' in section)
        headers += [f'Percentage among {population} with information',
                    f'{population.capitalize()} with information', f'Total {population}', 'Coverage (%)']
    writer.writerow(headers)
    for section in sections:
        for row in sorted(section['rows'], key=lambda row: not row.get('information_available', True)):
            row_type = ('category' if row['information_available'] else 'unavailable') if (
                'information_available' in row) else 'measure'
            values = [start_date, end_date, section['title'], row['label'], row['count'], row['percentage'], row_type]
            if demographics:
                values += [row.get('available_percentage'), section.get('coverage_count'),
                           section.get('coverage_total'), section.get('coverage_percentage')]
            writer.writerow(values)
    return response


def usage_sections(sections, group='usage'):
    labels = {'overview': 'Measure', 'top_datasets': 'Dataset', 'country': 'Country',
              'category': 'Researcher category', 'versions': 'Dataset / version',
              'account_age': 'Account creation period', 'resource_type': 'Resource type'}
    population = {'usage': 'Registered viewers', 'access': 'Approved users',
                  'submissions': 'Submitting authors'}[group]
    result = [dict(section) for section in sections]
    for section in result:
        key = section['key']
        if key == 'top_datasets':
            section['display_title'] = 'Top 10 datasets by unique registered viewers'
        section['display_cards'] = key == 'overview'
        section['label_header'] = labels.get(key, 'Metric')
        section['count_header'] = ('Count' if key == 'overview' else 'Submitted versions' if key == 'resource_type'
                                   else population)
        section['show_percentage'] = key not in ('overview', 'versions')
        section['percentage_header'] = ('Submitted versions (%)' if key == 'resource_type'
                                        else f'All {population.lower()} (%)')
        section['unavailable_label'] = 'Viewers' if group == 'usage' else population
        section['has_coverage'] = 'coverage_total' in section
        section['column_count'] = 4 if section['has_coverage'] else 3 if section['show_percentage'] else 2
    return result
