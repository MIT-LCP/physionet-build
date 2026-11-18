"""Credentialing metrics: monthly trends, the current queue, reapplications and annual cohorts."""
from collections import Counter
from itertools import groupby

from django.core.cache import cache
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone

from console.reporting import (
    coverage, date_bounds, elapsed_days, median_days, month_labels, percentile, period, report_csv, trend_report,
)
from user.models import CredentialApplication

Status = CredentialApplication.Status
APPROVED_STATUSES = (Status.ACCEPTED, Status.REVOKED)
# Withdrawn and pending applications have no decision.
HANDLED_STATUSES = (*APPROVED_STATUSES, Status.REJECTED)
ANNUAL_STATS_CACHE_KEY = 'console:credentialing:annual-stats:v1'


def credential_trend(start_date, end_date):
    start, end = date_bounds(start_date, end_date)
    values = {month: [[], []] for month in month_labels(start_date, end_date)}
    invalid = 0
    decisions = CredentialApplication.objects.filter(
        decision_datetime__gte=start, decision_datetime__lt=end,
        status__in=HANDLED_STATUSES,
    )
    for submitted, decided, status in decisions.values_list('application_datetime', 'decision_datetime', 'status'):
        days = (decided - submitted).total_seconds() / 86400
        if days < 0:
            invalid += 1
            continue
        values[period(decided)][1 if status == Status.REJECTED else 0].append(days)
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
    return CredentialApplication.objects.filter(
        status=Status.PENDING, application_datetime__lte=now,
    ).order_by('application_datetime', 'pk')


def credential_annual_stats():
    """All submission-year cohorts, using current statuses and valid timestamp pairs.

    Independent of the selected dates and read from every application, so it is cached briefly.
    """
    result = cache.get(ANNUAL_STATS_CACHE_KEY)
    if result is None:
        result = _credential_annual_stats()
        cache.set(ANNUAL_STATS_CACHE_KEY, result, 300)
    return result


def _credential_annual_stats():
    groups = {}
    fields = ('application_datetime', 'status', 'reference_contact_datetime',
              'reference_response_datetime', 'decision_datetime')
    for submitted, status, contacted, responded, decided in CredentialApplication.objects.values_list(
            *fields).iterator(chunk_size=2000):
        year = timezone.localtime(submitted).year
        group = groups.setdefault(year, {'statuses': Counter(), 'decision': [], 'contact': [], 'response': []})
        group['statuses'][status] += 1
        if status in HANDLED_STATUSES:
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
        accepted, revoked, rejected, withdrawn, pending = (counts[s] for s in (
            Status.ACCEPTED, Status.REVOKED, Status.REJECTED, Status.WITHDRAWN, Status.PENDING))
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


def credential_summary_report(stats):
    """The original seven-column annual CSV, kept stable for existing downloads.

    Values follow the current definitions: handled and approved include revoked credentials, and
    durations are fractional days or hours.
    """
    fields = ('count', 'processed', 'approved', 'time_to_decision', 'time_to_ref', 'time_to_reply')
    return {
        'id': 'credentialing-stats',
        'headers': ['Year', 'Total applications', 'Total handled (accepted + revoked + rejected)', 'Approved (%)',
                    'Decision time (days, median)', 'Time to contact reference (days, median)',
                    'Reference response time (hours, median)'],
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


def credential_stage_report(start_date, end_date):
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
        decision_datetime__gte=start, decision_datetime__lt=end, status__in=HANDLED_STATUSES,
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
    start, end = date_bounds(start_date, end_date)
    counts = {month: [0, 0, 0] for month in month_labels(start_date, end_date)}
    apps = CredentialApplication.objects.all()
    for submitted in apps.filter(application_datetime__gte=start, application_datetime__lt=end).values_list(
            'application_datetime', flat=True).iterator(chunk_size=2000):
        counts[period(submitted)][0] += 1
    for decided, status in apps.filter(
            decision_datetime__gte=start, decision_datetime__lt=end, status__in=HANDLED_STATUSES).values_list(
                'decision_datetime', 'status').iterator(chunk_size=2000):
        counts[period(decided)][2 if status == Status.REJECTED else 1] += 1
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
        approved = [row for row in entries if row[2] in APPROVED_STATUSES]
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
