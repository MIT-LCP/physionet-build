"""Aggregate console usage metrics."""

import csv
from collections import Counter
from datetime import datetime, time, timedelta

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import BooleanField, Case, Count, Exists, Max, Min, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone

from project.models import AccessLog, ActiveProject, Author, DataAccessRequest, PublishedAuthor, PublishedProject
from user.models import COUNTRIES, CredentialApplication, User


def usage_record_dates():
    """Cache dataset access-log bounds for five minutes, independently of filters."""
    key = 'console:usage:record-dates:v1'
    bounds = cache.get(key)
    if bounds is None:
        bounds = AccessLog.objects.filter(
            content_type=ContentType.objects.get_for_model(PublishedProject),
            object_id__in=PublishedProject.objects.filter(resource_type_id=0).values('pk'),
        ).aggregate(first=Min('creation_datetime'), last=Max('last_access_datetime'))
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
        'title': title, 'coverage_count': known, 'coverage_total': total,
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


def _request_months(requests, start_date, end_date):
    counts = {
        row['month'].strftime('%Y-%m'): row['count']
        for row in requests.order_by().annotate(month=TruncMonth('request_datetime'))
        .values('month').annotate(count=Count('pk'))
    }
    # Include zero months, but leave wholly empty selections consistent with other sections.
    if not counts:
        return []
    year, month = start_date.year, start_date.month
    rows = []
    while (year, month) <= (end_date.year, end_date.month):
        period = f'{year:04d}-{month:02d}'
        rows.append({'label': period, 'count': counts.get(period, 0), 'percentage': None})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return rows


def usage_metrics(start_date, end_date):
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    published_type = ContentType.objects.get_for_model(PublishedProject)
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
        {'title': 'Overview', 'description': (
            'All cards summarize the entire selected period, not the sum of monthly values. '
            'Each viewer is counted once, even if they appear in several months. Datasets combine all versions; '
            'institutions count distinct self-reported names, ignoring case and extra spaces. Spelling variants '
            'and abbreviations may still count separately. Approved viewers are a subset of the same unique '
            'viewers, using their latest currently approved credential application. '
            'Cards include sessions overlapping the selected dates. Monthly charts instead include sessions '
            'that started within those dates, so the two populations can differ.'),
         'rows': [{'label': label, 'count': count,
                   'percentage': round(100 * count / viewer_count, 2)
                   if label == 'Viewers with an approved credential application' and viewer_count else None}
                  for label, count in overview]},
        {'title': 'Most accessed datasets',
         'description': ('Top 10 by unique registered viewers, combining all versions. '
                         'A person may view multiple datasets.'),
         'rows': [{'label': row['slug'], 'count': row['count'],
                   'percentage': round(row['count'] * 100 / viewer_count, 2)} for row in top_datasets]},
        _viewer_demographic(viewers, 'credential_country', countries, 'Dataset viewers by country'),
        _viewer_demographic(viewers, 'credential_category', categories, 'Dataset viewers by researcher category'),
        {**_viewer_demographic(
            viewers, 'credential_course', dict(CredentialApplication.COURSE_CATEGORIES), 'Declared course use'),
         'csv_only': True},
        {'title': 'Registered viewers by dataset version',
         'description': 'Unique registered file-access viewers per version. A person may appear in multiple versions.',
         'rows': [{'label': f"{row['slug']} / {row['version']}", 'count': row['count'], 'percentage': None}
                  for row in version_views]},
        {'title': 'Dataset viewers by account age',
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
        {'title': 'Overview', 'description': '',
         'rows': [{'label': label, 'count': count,
                   'percentage': None}
                  for label, count in overview]},
        {'title': 'Dataset access requests by month',
         'description': ('Requests submitted during the selected dates, including requests now rejected, withdrawn '
                         'or revoked. Only datasets using contributor-reviewed access have these requests. '
                         'Boundary months may be partial.'),
         'rows': _request_months(requests, start_date, end_date)},
        _viewer_demographic(approved_users, 'credential_country', countries,
                            'Approved dataset users by country', population='approved users'),
        _viewer_demographic(approved_users, 'credential_category', categories,
                            'Approved dataset users by researcher category', population='approved users'),
        {'title': 'Approved dataset users by account age',
         'description': ('Users approved during the selected dates. New means the account was created during '
                         'those dates, not necessarily when access was requested.'),
         'rows': _account_age(approved_users, start_date, end_date)},
    ]


def usage_csv(sections, start_date, end_date):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="usage-stats.csv"'
    writer = csv.writer(response)
    demographics = any('coverage_total' in section for section in sections)
    headers = ['Start date', 'End date', 'Section', 'Metric', 'Count', 'Percentage', 'Row type']
    if demographics:
        approved = any(section['title'].startswith('Approved dataset users') for section in sections)
        population = ('approved users' if approved else 'submitting authors'
                      if any(s['title'].startswith('Submitting authors') for s in sections) else 'viewers')
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
    result = sections
    if group in ('usage', 'access', 'submissions'):
        labels = {'Overview': 'Measure', 'Most accessed datasets': 'Dataset',
                  'Dataset viewers by country': 'Country',
                  'Dataset viewers by researcher category': 'Researcher category',
                  'Registered viewers by dataset version': 'Dataset / version',
                  'Dataset viewers by account age': 'Account creation period',
                  'Approved dataset users by country': 'Country',
                  'Approved dataset users by researcher category': 'Researcher category',
                  'Approved dataset users by account age': 'Account creation period',
                  }
        result = [dict(section) for section in result]
        for section in result:
            if section['title'] == 'Most accessed datasets':
                section['display_title'] = 'Top 10 datasets by unique registered viewers'
            section['display_cards'] = group == 'usage' and section['title'] == 'Overview'
            section['label_header'] = labels.get(section['title'], 'Metric')
            population = {'usage': 'Registered viewers', 'access': 'Approved users',
                          'submissions': 'Submitting authors'}[group]
            section['count_header'] = 'Count' if section['title'] == 'Overview' else population
            section['show_percentage'] = section['title'] not in ('Overview', 'Registered viewers by dataset version')
            section['percentage_header'] = f'All {population.lower()} (%)'
            section['unavailable_label'] = 'Viewers' if group == 'usage' else population
            section['has_coverage'] = 'coverage_total' in section
            section['column_count'] = 4 if section['has_coverage'] else 3 if section['show_percentage'] else 2
    return result
