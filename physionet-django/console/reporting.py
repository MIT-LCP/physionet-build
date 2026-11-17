"""Definitions shared by monthly operational reports and their CSV exports."""
import csv
from calendar import monthrange
from datetime import datetime, time, timedelta
from statistics import median

from django.http import HttpResponse
from django.utils import timezone

from project.models import DataAccessRequest


def date_bounds(start_date, end_date):
    return (timezone.make_aware(datetime.combine(start_date, time.min)),
            timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min)))


def month_labels(start_date, end_date):
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        yield f'{year:04d}-{month:02d}'
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def period(value):
    return timezone.localtime(value).strftime('%Y-%m')


def median_days(values):
    return round(median(values), 2) if values else None


def trend_report(identifier, title, description, headers, rows, series,
                 start_date=None, end_date=None, integer=False, warning=''):
    partial = []
    for row in rows:
        year, month = map(int, row[0].split('-'))
        first = datetime(year, month, 1).date()
        last = first.replace(day=monthrange(year, month)[1])
        partial.append(bool(start_date and end_date and (
            start_date > first or end_date < last or first <= timezone.localdate() <= last)))
    if start_date and end_date:
        headers = [*headers, 'Period coverage']
        rows = [[*row, 'Partial month' if limited else 'Full month'] for row, limited in zip(rows, partial)]
    return {'id': identifier, 'title': title, 'description': description,
            'summary': description.partition('. ')[0].rstrip('.') + '.', 'warning': warning,
            'headers': headers, 'rows': rows,
            'chart': {'labels': [row[0] for row in rows], 'partial': partial, 'integer': integer, 'series': [
                {'name': name, 'values': [row[index] for row in rows]}
                for name, index in series
            ]}}


def report_csv(report):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{report["id"]}-{timezone.localdate()}.csv"'
    writer = csv.writer(response)
    writer.writerow(report['headers'])
    writer.writerows(report['rows'])
    return response


def access_trend(start_date, end_date):
    start, end = date_bounds(start_date, end_date)
    requests = DataAccessRequest.objects.filter(project__resource_type_id=0)
    counts = {month: [0, 0, 0] for month in month_labels(start_date, end_date)}
    for date in requests.filter(request_datetime__gte=start, request_datetime__lt=end).values_list(
            'request_datetime', flat=True):
        counts[period(date)][0] += 1
    decisions = requests.filter(
        decision_datetime__gte=start, decision_datetime__lt=end,
        status__in=(DataAccessRequest.ACCEPT_REQUEST_VALUE, DataAccessRequest.REVOKED_VALUE,
                    DataAccessRequest.REJECT_REQUEST_VALUE),
    )
    for date, status in decisions.values_list('decision_datetime', 'status'):
        counts[period(date)][2 if status == DataAccessRequest.REJECT_REQUEST_VALUE else 1] += 1
    rows = [[month, *values] for month, values in counts.items()]
    return trend_report(
        'access-monthly', 'Access requests and decisions by month',
        'Counts of contributor-reviewed dataset requests by request date and decisions by decision date. '
        'Approvals include later revocations and expiry. These are different cohorts, not an approval rate. '
        'Boundary months cover only selected dates; zero means no recorded events.',
        ['Period (YYYY-MM)', 'Requests submitted', 'Approvals', 'Rejections'], rows,
        [('Requests submitted', 1), ('Approvals', 2), ('Rejections', 3)], start_date, end_date, integer=True,
    )


def pending_access_requests(now):
    """Current queue, independent of the reporting period; oldest requests first."""
    return DataAccessRequest.objects.filter(
        project__resource_type_id=0, status=DataAccessRequest.PENDING_VALUE,
        request_datetime__lte=now,
    ).select_related('project').order_by('request_datetime', 'pk')


def access_queue_rows(requests, now):
    from django.urls import reverse
    return [{'label': f'{item.project.slug} / {item.project.version}', 'status': 'Pending access review',
             'dataset': item.project.slug, 'version': item.project.version,
             'since': item.request_datetime, 'days': (now - item.request_datetime).days,
             'url': reverse('access_request', args=[item.pk])} for item in requests]


def queue_csv(identifier, rows, item_label='Project or application', snapshot=None):
    if snapshot is not None:
        return report_csv({
            'id': identifier,
            'headers': ['Snapshot', 'Dataset', 'Version', 'Status', 'Since', 'Elapsed days (floor)'],
            'rows': [[snapshot.isoformat(), row['dataset'], row['version'], row['status'],
                      row['since'].isoformat(), row['days']] for row in rows],
        })
    return report_csv({'id': identifier, 'headers': [item_label, 'Status', 'Since', 'Elapsed days'],
                       'rows': [[row['label'], row['status'], row['since'].isoformat(), row['days']] for row in rows]})


def elapsed_days(start, end):
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() / 86400


ACCESS_AGE_LABELS = ('Under 7 days', '7–29 days', '30–89 days', '90–364 days', '365+ days')

ACCESS_QUEUE_COLUMNS = ['Pending requests', 'Unique requesters', 'Median age (days)', 'Oldest age (days)',
                        *ACCESS_AGE_LABELS]


def access_pending_summary(requests, now):
    """One snapshot; requests add across datasets, distinct people do not."""
    def bucket():
        return {'ages': [], 'users': set(), 'bands': [0] * 5}

    def add(group, item, age):
        group['ages'].append(age)
        group['users'].add(item.requester_id)
        band = sum(age >= boundary for boundary in (7, 30, 90, 365))
        group['bands'][band] += 1

    def cells(group):
        return [len(group['ages']), len(group['users']), median(group['ages']) if group['ages'] else None,
                max(group['ages']) if group['ages'] else None, *group['bands']]

    groups, total = {}, bucket()
    for item in requests:
        age = elapsed_days(item.request_datetime, now)
        if item.status != DataAccessRequest.PENDING_VALUE or age is None:
            continue
        slug, version = item.project.slug, item.project.version
        group = groups.setdefault(slug, {**bucket(), 'versions': {}})
        version_group = group['versions'].setdefault(version, bucket())
        for target in (group, version_group, total):
            add(target, item, age)
    rows = []
    for slug, group in sorted(groups.items(), key=lambda pair: (-len(pair[1]['ages']), pair[0])):
        rows.append({'label': slug, 'cells': cells(group), 'versions': [
            {'label': version, 'cells': cells(values)}
            for version, values in sorted(group['versions'].items(), key=lambda pair: (-len(pair[1]['ages']), pair[0]))
        ]})
    return {'title': 'Pending requests by dataset and age', 'snapshot': now, 'datasets': rows,
            'total': {'label': 'All datasets', 'cells': cells(total)}, 'columns': ACCESS_QUEUE_COLUMNS,
            'description': (
                'Current pending requests, independent of historical date filters. Dataset means project '
                'slug, combining all versions. Counts and age bands count individual requests, not people or '
                'person–version pairs. Unique requesters are deduplicated across versions within each dataset; '
                'the total deduplicates across the entire queue, so unique requester columns must not be summed. '
                'Ages are elapsed 24-hour days since request, not time in a stage. '
                'Summary ages are rounded to one decimal for display; '
                'individual queue ages use completed days (floor). '
                'Bands are [0,7), [7,30), [30,90), [90,365) and 365+. Median and oldest ages use the same snapshot. '
                'Future-dated requests are excluded. No projects are excluded by name.')}


def access_pending_summary_csv(summary, versions=False):
    def formatted(cells):
        return [round(value, 2) if i in (2, 3) and value is not None else value
                for i, value in enumerate(cells)]

    snapshot = summary['snapshot'].isoformat()
    rows = []
    for dataset in summary['datasets']:
        if versions:
            rows.extend([snapshot, 'dataset-version', dataset['label'], version['label'], *formatted(version['cells'])]
                        for version in dataset['versions'])
        else:
            rows.append([snapshot, 'dataset', dataset['label'], *formatted(dataset['cells'])])
    if not versions:
        rows.append([snapshot, 'total', summary['total']['label'], *formatted(summary['total']['cells'])])
    return report_csv({
        'id': 'pending-access-by-version' if versions else 'pending-access-by-dataset',
        'headers': ['Snapshot', 'Row type', 'Dataset', *(['Version'] if versions else []), *summary['columns']],
        'rows': rows,
    })
