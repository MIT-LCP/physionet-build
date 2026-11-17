"""Definitions shared by monthly operational reports and their CSV exports."""
import csv
from calendar import monthrange
from datetime import datetime, time, timedelta
from statistics import median

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.urls import reverse
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
    submitted = (requests.filter(request_datetime__gte=start, request_datetime__lt=end).order_by()
                 .annotate(month=TruncMonth('request_datetime')).values('month').annotate(count=Count('pk')))
    for row in submitted:
        counts[row['month'].strftime('%Y-%m')][0] += row['count']
    decisions = (requests.filter(
        decision_datetime__gte=start, decision_datetime__lt=end,
        status__in=(DataAccessRequest.ACCEPT_REQUEST_VALUE, DataAccessRequest.REVOKED_VALUE,
                    DataAccessRequest.REJECT_REQUEST_VALUE),
    ).order_by().annotate(month=TruncMonth('decision_datetime')).values('month', 'status').annotate(count=Count('pk')))
    for row in decisions:
        column = 2 if row['status'] == DataAccessRequest.REJECT_REQUEST_VALUE else 1
        counts[row['month'].strftime('%Y-%m')][column] += row['count']
    rows = [[month, *values] for month, values in counts.items()]
    report = trend_report(
        'access-monthly', 'Access requests and decisions by month',
        'Counts of contributor-reviewed dataset requests by request date and decisions by decision date. '
        'Approvals include later revocations and expiry. These are different cohorts, not an approval rate. '
        'Boundary months cover only selected dates; zero means no recorded events.',
        ['Period (YYYY-MM)', 'Requests submitted', 'Approvals', 'Rejections'], rows,
        [('Requests submitted', 1), ('Approvals', 2), ('Rejections', 3)], start_date, end_date, integer=True,
    )

    report['chart'].update({'period_unit': 'month', 'partial_through': end_date.isoformat(),
                            'interactive_legend': True, 'plot_height': 320,
                            'legend_title': 'Visible request and decision series'})
    for series, color, marker in zip(report['chart']['series'],
                                     ('#2563eb', '#15803d', '#b91c1c'), ('circle', 'triangle', 'diamond')):
        series.update({'color': color, 'marker': marker})
    return report


def pending_access_requests(now):
    """Current queue, independent of the reporting period; oldest requests first."""
    return DataAccessRequest.objects.filter(
        project__resource_type_id=0, status=DataAccessRequest.PENDING_VALUE,
        request_datetime__lte=now,
    ).select_related('project').order_by('request_datetime', 'pk')


def access_queue_rows(requests, now):
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


def credential_trend(start_date, end_date):
    from user.models import CredentialApplication
    start, end = date_bounds(start_date, end_date)
    values = {month: [[], []] for month in month_labels(start_date, end_date)}
    invalid = 0
    decisions = CredentialApplication.objects.filter(
        decision_datetime__gte=start, decision_datetime__lt=end,
        status__in=(CredentialApplication.Status.ACCEPTED, CredentialApplication.Status.REVOKED,
                    CredentialApplication.Status.REJECTED),
    )
    for submitted, decided, status in decisions.values_list('application_datetime', 'decision_datetime', 'status'):
        days = (decided - submitted).total_seconds() / 86400
        if days < 0:
            invalid += 1
            continue
        values[period(decided)][1 if status == CredentialApplication.Status.REJECTED else 0].append(days)
    rows = []
    for month, (accepted, rejected) in values.items():
        combined = accepted + rejected
        rows.append([month, median_days(accepted), len(accepted), median_days(rejected), len(rejected),
                     median_days(combined), percentile(combined, 0.9), len(combined),
                     coverage(sum(days <= 3 for days in combined), len(combined)),
                     coverage(sum(days <= 7 for days in combined), len(combined))])
    report = trend_report(
        'credentialing-monthly', 'Credentialing decision time by month',
        'Grouped by decision date, measuring calendar days from application to decision. '
        'Accepted includes later-revoked credentials. Withdrawals and pending applications are excluded. '
        'The chart combines accepted and rejected decisions and shows the median and p90 '
        '(90th percentile, using linear interpolation). The table and CSV retain separate outcomes. '
        'Within 3 or 7 days uses valid, non-negative decision durations only, not pending applications. '
        'Missing medians mean no valid observations; boundary months may be partial. '
        + (f'Excluded negative durations: {invalid}.' if invalid else ''),
        ['Period (YYYY-MM)', 'Accepted median days', 'Accepted valid durations',
         'Rejected median days', 'Rejected valid durations', 'Overall median days', 'Overall p90 days',
         'Valid decision durations', 'Decided within 3 days (%)', 'Decided within 7 days (%)'],
        rows, [('Overall median days', 5), ('Overall p90 days', 6)], start_date, end_date,
    )

    report['warning'] = f'Excluded negative durations: {invalid}.' if invalid else ''
    return report


def pending_credentials(now):
    from user.models import CredentialApplication
    return CredentialApplication.objects.filter(
        status=CredentialApplication.Status.PENDING, application_datetime__lte=now,
    ).order_by('application_datetime', 'pk')


def credential_queue_rows(applications, now):
    from django.urls import reverse
    rows = []
    labels = dict(CREDENTIAL_STAGES)
    for app in applications:
        status = labels[credential_stage(app.reference_contact_datetime, app.reference_response_datetime)]
        rows.append({'label': app.slug, 'status': status, 'since': app.application_datetime,
                     'days': (now - app.application_datetime).days,
                     'url': reverse('process_credential_application', args=[app.slug])})
    return rows


def repeated_credentials(start_date, end_date):
    from django.db.models import Count, Q
    from user.models import CredentialApplication
    start, end = date_bounds(start_date, end_date)
    apps = CredentialApplication.objects.filter(application_datetime__gte=start, application_datetime__lt=end)
    statuses = CredentialApplication.Status
    users = apps.order_by().values('user_id', 'user__username').annotate(
        total=Count('pk'),
        accepted=Count('pk', filter=Q(status__in=(statuses.ACCEPTED, statuses.REVOKED))),
        rejected=Count('pk', filter=Q(status=statuses.REJECTED)),
        withdrawn=Count('pk', filter=Q(status=statuses.WITHDRAWN)),
        pending=Count('pk', filter=Q(status=statuses.PENDING)),
    ).filter(total__gte=2).order_by('-total', 'user_id')
    return users


def repeated_credential_report(users):
    return {'id': 'repeated-credentialing',
            'headers': ['Username', 'Applications', 'Accepted (including revoked)',
                        'Rejected', 'Withdrawn', 'Pending'],
            'rows': [[u['user__username'], u['total'], u['accepted'], u['rejected'], u['withdrawn'], u['pending']]
                     for u in users]}


def elapsed_days(start, end):
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() / 86400


def coverage(valid, eligible):
    """Percentage with an explicit denominator; no eligible records means unavailable."""
    return round(100 * valid / eligible, 2) if eligible else None


def credential_annual_stats():
    """All submission-year cohorts, using current statuses and valid timestamp pairs."""
    from collections import Counter
    from user.models import CredentialApplication
    groups = {}
    fields = ('application_datetime', 'status', 'reference_contact_datetime',
              'reference_response_datetime', 'decision_datetime')
    for submitted, status, contacted, responded, decided in CredentialApplication.objects.values_list(
            *fields).iterator(chunk_size=2000):
        year = timezone.localtime(submitted).year
        group = groups.setdefault(year, {'statuses': Counter(), 'decision': [], 'contact': [], 'response': []})
        group['statuses'][status] += 1
        if status in (CredentialApplication.Status.ACCEPTED, CredentialApplication.Status.REVOKED,
                      CredentialApplication.Status.REJECTED):
            days = elapsed_days(submitted, decided)
            if days is not None:
                group['decision'].append(days)
        for label, first, last, multiplier in (
                ('contact', submitted, contacted, 1), ('response', contacted, responded, 24)):
            days = elapsed_days(first, last)
            if days is not None:
                group[label].append(days * multiplier)
    result = {}
    for year, group in sorted(groups.items()):
        counts = group['statuses']
        accepted, revoked, rejected, withdrawn, pending = (counts[s] for s in (2, 4, 1, 3, 0))
        processed = accepted + revoked + rejected
        result[year] = {
            'count': sum(counts.values()), 'accepted': accepted, 'revoked': revoked, 'rejected': rejected,
            'withdrawn': withdrawn, 'pending': pending, 'processed': processed,
            'approved': round(100 * (accepted + revoked) / processed, 2) if processed else None,
            'time_to_decision': median_days(group['decision']), 'decision_observations': len(group['decision']),
            'time_to_ref': median_days(group['contact']), 'contact_observations': len(group['contact']),
            'time_to_reply': median_days(group['response']), 'response_observations': len(group['response']),
            'decision_coverage': coverage(len(group['decision']), processed),
            'contact_coverage': coverage(len(group['contact']), sum(counts.values())),
            'response_coverage': coverage(len(group['response']), sum(counts.values())),
        }
    return result


def credential_annual_report(stats):
    fields = ('count', 'accepted', 'revoked', 'rejected', 'withdrawn', 'pending', 'processed', 'approved',
              'time_to_decision', 'decision_observations', 'time_to_ref', 'contact_observations',
              'time_to_reply', 'response_observations', 'decision_coverage', 'contact_coverage', 'response_coverage')
    return {
        'id': 'credentialing-annual',
        'headers': ['Application year', 'Total applications', 'Accepted', 'Revoked', 'Rejected', 'Withdrawn',
                    'Pending', 'Handled (accepted + revoked + rejected)', 'Ever approved among handled (%)',
                    'Decision median days', 'Valid decision durations', 'Contact median days',
                    'Valid contact durations', 'Response median hours', 'Valid response durations',
                    'Decision coverage among handled (%)', 'Contact coverage among all applications (%)',
                    'Response coverage among all applications (%)'],
        'rows': [[year, *(values[field] for field in fields)] for year, values in stats.items()],
    }


CREDENTIAL_STAGES = (
    ('contact', 'Awaiting reference contact'),
    ('response', 'Awaiting reference response'),
    ('processing', 'Awaiting processing after reference response'),
)

CREDENTIAL_AGES = (
    ('under7', 'Under 7 days'), ('7to29', '7–29 days'),
    ('30to89', '30–89 days'), ('90plus', '90+ days'),
)


def credential_stage(contacted, responded):
    return 'contact' if contacted is None else 'response' if responded is None else 'processing'


def credential_queue_summary(now):
    counts = {stage: [0, 0, 0, 0] for stage, _ in CREDENTIAL_STAGES}
    for submitted, contacted, responded in pending_credentials(now).values_list(
            'application_datetime', 'reference_contact_datetime', 'reference_response_datetime').iterator():
        days = (now - submitted).days
        index = 0 if days < 7 else 1 if days < 30 else 2 if days < 90 else 3
        counts[credential_stage(contacted, responded)][index] += 1
    rows = [[label, *counts[stage], sum(counts[stage])] for stage, label in CREDENTIAL_STAGES]
    rows.append(['Total', *[sum(row[index] for row in rows) for index in range(1, 6)]])
    return {'id': 'credentialing-current-queue-summary', 'title': 'Current pending applications by stage and age',
            'summary': 'Current pending applications by stage and age, across all dates.',
            'description': 'Current pending applications, independent of historical dates and queue filters. '
                           'Age is measured from application submission, not from entry into the current stage.',
            'headers': ['Stage', *[label for _, label in CREDENTIAL_AGES], 'Total'], 'rows': rows}


def filter_credential_queue(queue, stage, age, now):
    from django.http import Http404
    if stage not in ('', *dict(CREDENTIAL_STAGES)) or age not in ('', *dict(CREDENTIAL_AGES)):
        raise Http404('Unknown credentialing queue filter')
    if stage == 'contact':
        queue = queue.filter(reference_contact_datetime__isnull=True)
    elif stage == 'response':
        queue = queue.filter(reference_contact_datetime__isnull=False, reference_response_datetime__isnull=True)
    elif stage == 'processing':
        queue = queue.filter(reference_contact_datetime__isnull=False, reference_response_datetime__isnull=False)
    if age == 'under7':
        queue = queue.filter(application_datetime__gt=now - timedelta(days=7))
    elif age == '7to29':
        queue = queue.filter(application_datetime__lte=now - timedelta(days=7),
                             application_datetime__gt=now - timedelta(days=30))
    elif age == '30to89':
        queue = queue.filter(application_datetime__lte=now - timedelta(days=30),
                             application_datetime__gt=now - timedelta(days=90))
    elif age == '90plus':
        queue = queue.filter(application_datetime__lte=now - timedelta(days=90))
    return queue


def percentile(values, fraction):
    """Linearly interpolated percentile; round only the final result."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 2)


def credential_stage_report(start_date, end_date):
    from user.models import CredentialApplication
    start, end = date_bounds(start_date, end_date)
    stages = [
        ('Application → reference contact', 0, 1),
        ('Reference contact → response', 1, 2),
        ('Reference response → decision', 2, 3),
        ('Application → decision', 0, 3),
    ]
    values = [[] for _ in stages]
    missing = [0] * len(stages)
    negative = [0] * len(stages)
    apps = CredentialApplication.objects.filter(
        decision_datetime__gte=start, decision_datetime__lt=end, status__in=(1, 2, 4),
    ).values_list('application_datetime', 'reference_contact_datetime', 'reference_response_datetime',
                  'decision_datetime')
    for timestamps in apps.iterator(chunk_size=2000):
        for index, (_, first, last) in enumerate(stages):
            left, right = timestamps[first], timestamps[last]
            if left is None or right is None:
                missing[index] += 1
            elif right < left:
                negative[index] += 1
            else:
                values[index].append(elapsed_days(left, right))
    eligible = len(values[0]) + missing[0] + negative[0]
    return {
        'id': 'credentialing-stage-durations', 'title': 'Time between credentialing steps',
        'summary': ('Compare median and p90 time between steps for handled applications '
                    'decided in the selected period. Medians are not additive; each step can use a different subset.'),
        'description': 'Handled applications with a decision during the selected dates, including later revocations. '
                       'Each timestamp pair is checked independently; missing and negative intervals are excluded '
                       'and counted separately. Durations use fractional calendar days, including zero. '
                       'Medians are not additive: steps use different subsets and must not be summed. '
                       'Coverage = valid observations / all handled applications decided in the selected period. '
                       'Missing timestamps do not establish whether a step occurred; their cause is unknown. '
                       'Fewer than 10 observations is a descriptive warning, not a reliability threshold. '
                       'P90 uses linear interpolation.',
        'headers': ['Interval', 'Valid observations', 'Median days', 'P90 days',
                    'Missing pairs', 'Negative intervals', 'Eligible applications', 'Coverage (%)', 'Sample note'],
        'rows': [[name, len(values[i]), median_days(values[i]), percentile(values[i], 0.9), missing[i], negative[i],
                  eligible, coverage(len(values[i]), eligible),
                  'Fewer than 10 observations' if 0 < len(values[i]) < 10 else '']
                 for i, (name, _, _) in enumerate(stages)],
    }


def credential_flow_report(start_date, end_date):
    from user.models import CredentialApplication
    start, end = date_bounds(start_date, end_date)
    counts = {month: [0, 0, 0] for month in month_labels(start_date, end_date)}
    apps = CredentialApplication.objects.all()
    for submitted in apps.filter(application_datetime__gte=start, application_datetime__lt=end).values_list(
            'application_datetime', flat=True).iterator(chunk_size=2000):
        counts[period(submitted)][0] += 1
    for decided, status in apps.filter(
            decision_datetime__gte=start, decision_datetime__lt=end, status__in=(1, 2, 4)).values_list(
                'decision_datetime', 'status').iterator(chunk_size=2000):
        counts[period(decided)][2 if status == 1 else 1] += 1
    rows = [[month, received, accepted, rejected, accepted + rejected]
            for month, (received, accepted, rejected) in counts.items()]
    report = trend_report(
        'credentialing-flow', 'Applications received versus decisions by month',
        'Applications are counted by submission date; decisions by decision date. Accepted includes later '
        'revocations. These are different cohorts, so their difference is not a reconstructed backlog or '
        'an approval rate. Withdrawals are not decisions. Recorded decisions count even if their duration '
        'is invalid or unavailable; the decision-time chart excludes invalid durations.',
        ['Period (YYYY-MM)', 'Applications received', 'Accepted decisions',
         'Rejected decisions', 'Decisions recorded'],
        rows, [('Accepted decisions', 2), ('Rejected decisions', 3), ('Applications received', 1)],
        start_date, end_date, integer=True,
    )
    report['chart']['type'] = 'stacked-bar-line'
    for index, series in enumerate(report['chart']['series']):
        series['type'] = 'bar' if index < 2 else 'line'
    report['summary'] = ('Accepted and rejected decisions (stacked bars) and applications received (line), '
                         'on one count axis.')
    return report


def credential_reapplication_reports(start_date, end_date):
    from collections import Counter
    from itertools import groupby
    from user.models import CredentialApplication
    start, end = date_bounds(start_date, end_date)
    cohort = CredentialApplication.objects.filter(
        application_datetime__gte=start, application_datetime__lt=end,
    ).order_by().values('user_id')
    history = CredentialApplication.objects.filter(user_id__in=cohort).order_by(
        'user_id', 'application_datetime', 'pk').values_list(
            'user_id', 'application_datetime', 'status', 'decision_datetime')
    applications = Counter()
    attempts = Counter()
    latest = Counter()
    total = repeats = 0
    for _, entries in groupby(history.iterator(chunk_size=2000), key=lambda row: row[0]):
        entries = list(entries)
        total += 1
        repeats += len(entries) >= 2
        applications[min(4, len(entries))] += 1
        latest[entries[-1][2]] += 1
        approved = [row for row in entries if row[2] in (2, 4)]
        valid = [row[3] for row in approved if row[3] is not None and row[3] >= row[1]]
        if valid:
            first_approval = min(valid)
            attempts[min(4, sum(row[1] <= first_approval for row in entries))] += 1
        elif approved:
            attempts['missing'] += 1
        else:
            attempts['none'] += 1

    def rows(counts, labels):
        return [[label, counts[key], round(100 * counts[key] / total, 2) if total else None]
                for key, label in labels]
    labels = [(1, '1 application'), (2, '2 applications'), (3, '3 applications'), (4, '4+ applications')]
    common = ('People with at least one application submitted during the selected dates; calculations use their '
              'complete recorded history, including applications outside the selected dates. Percentages use all '
              f'{total} people in this cohort. Current statuses are used, not historical status snapshots. ')
    headers = ['Metric', 'Users', 'Percentage of cohort (%)']
    share = round(100 * repeats / total, 2) if total else 0
    return [
        {'id': 'credentialing-reapplication-distribution', 'title': 'Applications per person across complete history',
         'summary': f'{repeats} of {total} people ({share}%) have two or more recorded applications.',
         'description': common + f'{repeats} people ({share}%) have two or more recorded applications.',
         'headers': headers, 'rows': rows(applications, labels)},
        {'id': 'credentialing-first-approval', 'title': 'Applications until first approval',
         'summary': 'Applications submitted up to the first valid approval date, using complete recorded histories.',
         'description': common + (
             'Counts applications submitted on or before the earliest valid approval date. '
             'Later-revoked credentials count as approvals. Missing or negative approval dates are '
             'reported separately; this does not measure current eligibility. '
             'Percentages use everyone in the selected cohort, including people without a recorded approval.'),
         'headers': headers, 'rows': rows(attempts, [
             *labels,
             ('none', 'No recorded approval'),
             ('missing', 'Approved record without a valid decision date')])},
        {'id': 'credentialing-latest-application', 'title': "Latest application's current status",
         'summary': 'Current status of the latest application for each person in the selected cohort.',
         'description': common + (
             'One latest application per person, ordered by submission time and record ID. '
             'This describes that application, not the account credentialing status.'),
         'headers': headers, 'rows': rows(latest, [
             (status.value, status.label) for status in CredentialApplication.Status])},
    ]


def credential_reapplication_csv(reports):
    return report_csv({'id': 'credentialing-reapplication-summary',
                       'headers': ['Section', 'Metric', 'Users', 'Percentage of cohort (%)'],
                       'rows': [[report['title'], *row] for report in reports for row in report['rows']]})


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
                'Summary ages are rounded to one decimal on screen and two in the CSV; '
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
