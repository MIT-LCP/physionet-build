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
             'since': item.request_datetime, 'days': (now - item.request_datetime).days,
             'url': reverse('access_request', args=[item.pk])} for item in requests]


def queue_csv(identifier, rows, item_label='Project or application'):
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
    rows = [[month, median_days(accepted), len(accepted), median_days(rejected), len(rejected)]
            for month, (accepted, rejected) in values.items()]
    report = trend_report(
        'credentialing-monthly', 'Credentialing decision time by month',
        'Grouped by decision date, measuring calendar days from application to decision. '
        'Accepted includes later-revoked credentials. Withdrawals and pending applications are excluded. '
        'Missing medians mean no valid observations; boundary months may be partial. '
        + (f'Excluded negative durations: {invalid}.' if invalid else ''),
        ['Period (YYYY-MM)', 'Accepted median days', 'Accepted decisions',
         'Rejected median days', 'Rejected decisions'],
        rows, [('Accepted median days', 1), ('Rejected median days', 3)], start_date, end_date,
    )

    report['warning'] = f'Excluded negative durations: {invalid}.' if invalid else ''
    report['volume'] = {
        'id': 'credentialing-volume', 'title': 'Credentialing decision volume by month',
        'summary': 'Accepted and rejected decisions included in the decision-time analysis.',
        'description': 'Counts of the valid decisions included in the time analysis above, grouped by decision month. '
                       'Accepted includes later-revoked credentials. Boundary months may be partial. '
                       'The monthly table above and its CSV contain the values for both charts.',
        'chart': {'type': 'stacked-bar', 'integer': True, 'labels': [row[0] for row in rows],
                  'partial': report['chart']['partial'], 'series': [
            {'name': 'Accepted decisions', 'values': [row[2] for row in rows]},
            {'name': 'Rejected decisions', 'values': [row[4] for row in rows]},
        ]},
    }
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


def editorial_trend(start_date, end_date):
    from django.db.models import Exists, Min, OuterRef, Q
    from project.models import ActiveProject, PublishedProject
    start, end = date_bounds(start_date, end_date)
    published_version = PublishedProject.objects.filter(
        core_project_id=OuterRef('core_project_id'), version=OuterRef('version'),
    )
    active = ActiveProject.objects.annotate(published=Exists(published_version)).filter(published=False)
    values = {month: [] for month in month_labels(start_date, end_date)}
    invalid = 0
    for projects in (PublishedProject.objects.filter(is_legacy=False), active):
        observations = projects.filter(submission_datetime__isnull=False).annotate(
            first_decision=Min('edit_logs__decision_datetime', filter=Q(edit_logs__decision__in=(0, 1, 2))),
        ).filter(first_decision__gte=start, first_decision__lt=end)
        for submitted, decided in observations.values_list('submission_datetime', 'first_decision'):
            days = (decided - submitted).total_seconds() / 86400
            if days < 0:
                invalid += 1
                continue
            values[period(decided)].append(days)
    rows = [[month, median_days(days), len(days)] for month, days in values.items()]
    return trend_report(
        'editorial-monthly', 'Time to first editorial decision by month',
        'One observation per submitted project version, grouped by first decision month. '
        'Calendar days from initial submission to the earliest recorded accept, revise or reject decision. '
        'Includes active and archived projects and non-legacy publications; published snapshots take precedence '
        'over active copies. Missing submission or decision dates are omitted. Pending projects do not contribute '
        'to medians. Boundary months may be partial; missing medians mean no valid observations. '
        + (f'Excluded negative durations: {invalid}.' if invalid else ''),
        ['Period (YYYY-MM)', 'Median days to first decision', 'Project versions with a decision'], rows,
        [('Median days to first decision', 1)], start_date, end_date,
        warning=f'Excluded negative durations: {invalid}.' if invalid else '',
    )


def pending_projects(now):
    from project.models import ActiveProject, SubmissionStatus
    return ActiveProject.objects.filter(
        submission_status__gt=SubmissionStatus.ARCHIVED, submission_datetime__lte=now,
    ).order_by('submission_datetime', 'pk')


def project_queue_rows(projects, now):
    from django.urls import reverse
    return [{'label': project.slug,
             'status': project.submission_status_label() + (' (on hold)' if project.is_on_hold else ''),
             'since': project.submission_datetime, 'days': (now - project.submission_datetime).days,
             'url': reverse('submission_info', args=[project.slug])} for project in projects]


def elapsed_days(start, end):
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() / 86400


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
        }
    return result


def credential_annual_report(stats):
    fields = ('count', 'accepted', 'revoked', 'rejected', 'withdrawn', 'pending', 'processed', 'approved',
              'time_to_decision', 'decision_observations', 'time_to_ref', 'contact_observations',
              'time_to_reply', 'response_observations')
    return {
        'id': 'credentialing-annual',
        'headers': ['Application year', 'Total applications', 'Accepted', 'Revoked', 'Rejected', 'Withdrawn',
                    'Pending', 'Handled (accepted + revoked + rejected)', 'Ever approved among handled (%)',
                    'Decision median days', 'Valid decision durations', 'Contact median days',
                    'Valid contact durations', 'Response median hours', 'Valid response durations'],
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
    return {
        'id': 'credentialing-stage-durations', 'title': 'Time between credentialing steps',
        'summary': ('Compare median and p90 time between steps for handled applications '
                    'decided in the selected period.'),
        'description': 'Handled applications with a decision during the selected dates, including later revocations. '
                       'Each timestamp pair is checked independently; missing and negative intervals are excluded '
                       'and counted separately. Durations use fractional calendar days, including zero. '
                       'Medians for different steps must not be added. P90 uses linear interpolation.',
        'headers': ['Interval', 'Valid observations', 'Median days', 'P90 days',
                    'Missing pairs', 'Negative intervals'],
        'rows': [[name, len(values[i]), median_days(values[i]), percentile(values[i], 0.9), missing[i], negative[i]]
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
    return trend_report(
        'credentialing-flow', 'Applications received versus decisions by month',
        'Applications are counted by submission date; decisions by decision date. Accepted includes later '
        'revocations. These are different cohorts, so their difference is not a reconstructed backlog or '
        'an approval rate. Withdrawals are not decisions. Recorded decisions count even if their duration '
        'is invalid or unavailable; the decision-time chart excludes invalid durations.',
        ['Period (YYYY-MM)', 'Applications received', 'Accepted decisions',
         'Rejected decisions', 'Decisions recorded'],
        rows, [('Applications received', 1), ('Decisions recorded', 4)], start_date, end_date, integer=True,
    )


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
        {'id': 'credentialing-reapplication-distribution', 'title': 'Applications per person',
         'summary': f'{repeats} of {total} people ({share}%) have two or more recorded applications.',
         'description': common + f'{repeats} people ({share}%) have two or more recorded applications.',
         'headers': headers, 'rows': rows(applications, labels)},
        {'id': 'credentialing-first-approval', 'title': 'Applications submitted by first recorded approval',
         'summary': 'Applications submitted up to the first valid approval date, using complete recorded histories.',
         'description': common + (
             'Counts applications submitted on or before the earliest valid approval date. '
             'Later-revoked credentials count as approvals. Missing or negative approval dates are '
             'reported separately; this does not measure current eligibility.'),
         'headers': headers, 'rows': rows(attempts, [
             *labels,
             ('none', 'No accepted or revoked application in recorded history'),
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
