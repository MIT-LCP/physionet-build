"""Monthly unique approved requesters and the available dataset-request history."""
from collections import Counter

from django.core.cache import cache
from django.db.models import Max, Min
from django.db.models.functions import TruncMonth
from django.utils import timezone

from console.reporting import date_bounds, month_labels, trend_report
from console.usage import _demographics
from project.models import DataAccessRequest
from user.models import COUNTRIES, CredentialApplication, User


ACCESS_DESCRIPTION = (
    'Contributor-reviewed dataset requests only. Requests are grouped by submission date; approvals by decision '
    'date, including later revocations and expiry. These are different cohorts and must not be interpreted as '
    'an approval rate or a count of users with current access. '
    'Demographics use each person’s latest approved credential application currently on record, not a historical '
    'snapshot. Countries are institutional countries, not inferred locations or nationalities. People without '
    'an approved credential application are listed separately from approved applications with missing or '
    'unrecognized information. Institution counts use self-reported names, ignoring case and extra spaces; '
    'abbreviations and spelling variations may still count as separate institutions. Access approvals cover '
    'contributor-reviewed requests, not DUA signatures or every access requirement. Research purposes are free '
    'text and are not classified here.'
)


ACCESS_DATES_CACHE_KEY = 'console:access-requests:record-dates:v1'
COLORS = ['#2563eb', '#ea580c', '#15803d', '#b91c1c', '#7c3aed', '#0891b2', '#a16207', '#be185d']
MARKERS = ['circle', 'square', 'triangle', 'diamond', 'plus', 'cross', 'triangle-down', 'hexagon']


def access_record_dates():
    bounds = cache.get(ACCESS_DATES_CACHE_KEY)
    if bounds is None:
        dates = DataAccessRequest.objects.filter(project__resource_type_id=0).aggregate(
            first_request=Min('request_datetime'), first_decision=Min('decision_datetime'),
            last_request=Max('request_datetime'), last_decision=Max('decision_datetime'),
        )
        first = [dates[key] for key in ('first_request', 'first_decision') if dates[key]]
        last = [dates[key] for key in ('last_request', 'last_decision') if dates[key]]
        bounds = {'first': min(first) if first else None, 'last': max(last) if last else None}
        cache.set(ACCESS_DATES_CACHE_KEY, bounds, 300)
    return {key: timezone.localdate(value) if value else None for key, value in bounds.items()}


def approved_user_trends(start_date, end_date):
    """Deduplicate across versions within each month and across months for ranking."""
    start, end = date_bounds(start_date, end_date)
    approvals = DataAccessRequest.objects.filter(
        project__resource_type_id=0, decision_datetime__gte=start, decision_datetime__lt=end,
        status__in=(DataAccessRequest.ACCEPT_REQUEST_VALUE, DataAccessRequest.REVOKED_VALUE),
    )
    people = {
        row['pk']: row for row in _demographics(User.objects.filter(pk__in=approvals.values('requester_id')))
        .values('pk', 'credential_id', 'credential_country', 'credential_category')
    }
    months = list(month_labels(start_date, end_date))
    labels = {'country': dict(COUNTRIES), 'category': dict(CredentialApplication.RESEARCHER_CATEGORIES)}

    def group(person, field):
        if not person['credential_id']:
            return '__no_approval__'
        value = person['credential_' + field]
        return value if value in labels[field] else '__missing__'

    totals = {field: Counter(group(person, field) for person in people.values()) for field in labels}
    counts = {field: {month: Counter() for month in months} for field in labels}
    for month, user_id in approvals.order_by().annotate(month=TruncMonth('decision_datetime')).values_list(
            'month', 'requester_id').distinct():
        for field in labels:
            counts[field][month.strftime('%Y-%m')][group(people[user_id], field)] += 1

    reports = {}
    for field in labels:
        recognized = sorted((key for key in totals[field] if key in labels[field]),
                            key=lambda key: (-totals[field][key], str(labels[field][key])))
        plotted = recognized[:5] if field == 'country' else recognized
        names = {**labels[field], '__no_approval__': 'No approved credential application',
                 '__missing__': 'Information missing or unrecognized'}
        exported = [*recognized, '__no_approval__', '__missing__']
        rows = []
        for month in months:
            values = counts[field][month]
            total = sum(values.values())
            known = sum(values[key] for key in recognized)
            rows.append([month, *[values[key] for key in exported], known, total,
                         round(100 * known / total, 2) if total else None])
        description = (
            'Unique people approved for contributor-reviewed dataset access, counted by decision month in the '
            'site time zone. Each person is counted once per month across all dataset versions, and may appear '
            'in several months. Do not sum monthly people to get the period total. Approvals include later '
            'revocations and expiry; these are not counts of users with current access. Demographics use the '
            'latest currently approved credential application, not the profile at the time of access approval. '
            'Countries are institutional countries, not locations or nationalities. Missing and unrecognized '
            'values and people without an approved credential application are excluded from the lines but '
            'included in the table and CSV. Series are ranked by distinct people over the selected period.'
        )
        title = ('Approved dataset users by country and month' if field == 'country' else
                 'Approved dataset users by researcher category and month')
        report = trend_report(
            'access-' + field + '-monthly', title, description,
            ['Period (YYYY-MM)', *[str(names[key]) for key in exported],
             'Users with information', 'Unique approved users', 'Coverage (%)'], rows, [],
            start_date, end_date, integer=True,
        )
        report['chart'].update({
            'interactive_legend': True, 'plot_height': 440, 'line_width': 2,
            'legend_title': 'Visible countries' if field == 'country' else 'Visible researcher categories',
            'period_population': 'unique approved users',
            'period_unit': 'month', 'partial_through': end_date.isoformat(),
            'series': [
                {'name': str(names[key]), 'values': [counts[field][month][key] for month in months],
                 'color': COLORS[index % len(COLORS)], 'marker': MARKERS[index % len(MARKERS)],
                 'period_count': totals[field][key]}
                for index, key in enumerate(plotted)
            ],
        })
        report['summary'] = ('Top 5 countries, fixed across months. ' if field == 'country' else '') + (
            'Unique approved users per decision month. Uses currently recorded credential information.')
        reports[field] = report
    return reports


def pending_request_trend(requests, now):
    """Submission-month distribution of the current queue, never a historical backlog."""
    snapshot_date = timezone.localdate(now)
    counts = Counter(timezone.localtime(item.request_datetime).strftime('%Y-%m') for item in requests)
    first = min((timezone.localdate(item.request_datetime) for item in requests), default=snapshot_date)
    first = first.replace(day=1)
    report = trend_report(
        'access-pending-monthly', 'Current pending dataset access requests by request month',
        'Currently pending requests grouped by their original request month in the site time zone. '
        'This is the submission-month distribution of the current queue, not the queue size at past dates. '
        'Closed requests are excluded from every month. Each request is counted once; people may have '
        'multiple requests across datasets and versions. The selected dates do not filter this snapshot.',
        ['Request month (YYYY-MM)', 'Currently pending requests', 'Snapshot'],
        [[month, counts[month], now.isoformat()] for month in month_labels(first, snapshot_date)],
        [('Currently pending requests', 1)], first, snapshot_date, integer=True,
    )
    report['summary'] = ('Current pending requests grouped by original request month. '
                         'This is not historical queue size; selected dates do not apply.')
    report['chart'].update({'legend': False, 'period_unit': 'month',
                            'partial_through': snapshot_date.isoformat(), 'plot_height': 320})
    report['chart']['series'][0].update({'color': '#ea580c', 'marker': 'circle'})
    report['start_date'] = first
    report['end_date'] = snapshot_date
    return report
