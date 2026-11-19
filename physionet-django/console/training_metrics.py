"""Training submissions, approvals, review times, the review queue and upcoming expirations."""
from collections import Counter
from statistics import median

from django.core.cache import cache
from django.db.models import Case, CharField, Count, Max, Min, Q, Value, When
from django.db.models.functions import TruncMonth
from django.utils import timezone

from console.reporting import date_bounds, month_labels, percentile, period, trend_report
from user.enums import RequiredField, TrainingStatus
from user.models import Training

TRAINING_DESCRIPTION = (
    'Off-platform trainings are completion reports or links reviewed on PhysioNet, such as CITI courses; '
    'on-platform trainings are courses taken on PhysioNet. Submissions are grouped by submission date and '
    'acceptances by acceptance date, in the site time zone. Automatic approvals were verified through the CITI '
    'integration without a reviewer. On-platform courses record the date the course was started, not completed, '
    'so they are grouped by start month. Withdrawals record no date and appear only as the current outcome of '
    'submissions. Deleted trainings and accounts are not counted.'
)

TRAINING_DATES_CACHE_KEY = 'console:training:record-dates:v1'
OFF_PLATFORM = Q(training_type__required_field__in=(RequiredField.DOCUMENT, RequiredField.URL))
OUTCOMES = ((TrainingStatus.ACCEPTED, 'Accepted', '#15803d'), (TrainingStatus.REJECTED, 'Rejected', '#b91c1c'),
            (TrainingStatus.WITHDRAWN, 'Withdrawn', '#64748b'), (TrainingStatus.REVIEW, 'Awaiting review', '#ea580c'))
PATHS = (('automatic', 'Automatic (CITI)', '#2563eb'), ('manual', 'Manual review', '#ea580c'),
         ('platform', 'On-platform course', '#15803d'))
QUEUE_BANDS = (('Under 7 days', 0, 7), ('7–29 days', 7, 30), ('30–89 days', 30, 90), ('90 days or more', 90, None))
EXPIRY_BANDS = ('Expired', 'Expires within 30 days', 'Expires in 30–59 days', 'Expires in 60–89 days',
                'Expires in 90 days or more', 'Does not expire')


def _stamp(now):
    return timezone.localtime(now).strftime('%b %d, %Y %H:%M')


def training_record_dates():
    bounds = cache.get(TRAINING_DATES_CACHE_KEY)
    if bounds is None:
        bounds = Training.objects.aggregate(first=Min('application_datetime'), last=Max('application_datetime'))
        cache.set(TRAINING_DATES_CACHE_KEY, bounds, 300)
    return {key: timezone.localdate(value) if value else None for key, value in bounds.items()}


def _style(report, end_date, legend_title, colors, chart_type=None, markers=None):
    report['chart'].update({'period_unit': 'month', 'partial_through': end_date.isoformat(),
                            'interactive_legend': True, 'plot_height': 320, 'legend_title': legend_title})
    if chart_type:
        report['chart']['type'] = chart_type
    for index, (series, color) in enumerate(zip(report['chart']['series'], colors)):
        series['color'] = color
        if markers:
            series['marker'] = markers[index]
    return report


def submission_trend(start_date, end_date):
    start, end = date_bounds(start_date, end_date)
    counts = {month: Counter() for month in month_labels(start_date, end_date)}
    for row in (Training.objects.filter(OFF_PLATFORM, application_datetime__gte=start, application_datetime__lt=end)
                .order_by().annotate(month=TruncMonth('application_datetime')).values('month', 'status')
                .annotate(count=Count('pk'))):
        counts[row['month'].strftime('%Y-%m')][row['status']] += row['count']
    rows = [[month, sum(values.values()), *[values[status] for status, _, _ in OUTCOMES]]
            for month, values in counts.items()]
    report = trend_report(
        'training-monthly', 'Training submissions by month and current outcome',
        'Off-platform training submissions by submission month, split by their outcome today. Recent months '
        'still have submissions awaiting review. ' + TRAINING_DESCRIPTION,
        ['Period (YYYY-MM)', 'Submitted', *[label for _, label, _ in OUTCOMES]], rows,
        [(label, index + 2) for index, (_, label, _) in enumerate(OUTCOMES)], start_date, end_date, integer=True,
    )
    return _style(report, end_date, 'Visible outcomes', [color for _, _, color in OUTCOMES], 'stacked-bar')


def approval_trend(start_date, end_date):
    start, end = date_bounds(start_date, end_date)
    counts = {month: Counter() for month in month_labels(start_date, end_date)}
    path = Case(
        When(training_type__required_field=RequiredField.PLATFORM, then=Value('platform')),
        When(citi_verification__auto_approved=True, then=Value('automatic')),
        default=Value('manual'), output_field=CharField(),
    )
    accepted = Training.objects.filter(status=TrainingStatus.ACCEPTED, process_datetime__gte=start,
                                       process_datetime__lt=end).annotate(path=path)
    for row in (accepted.order_by().annotate(month=TruncMonth('process_datetime')).values('month', 'path')
                .annotate(count=Count('pk'))):
        counts[row['month'].strftime('%Y-%m')][row['path']] += row['count']
    rows = [[month, sum(values.values()), *[values[path] for path, _, _ in PATHS]] for month, values in counts.items()]
    report = trend_report(
        'training-approvals-monthly', 'Accepted trainings by month and approval path',
        'Accepted trainings by acceptance month, split into automatic CITI approvals, manual reviews and '
        'on-platform courses. ' + TRAINING_DESCRIPTION,
        ['Period (YYYY-MM)', 'Accepted', *[label for _, label, _ in PATHS]], rows,
        [(label, index + 2) for index, (_, label, _) in enumerate(PATHS)], start_date, end_date, integer=True,
    )
    return _style(report, end_date, 'Visible approval paths', [color for _, _, color in PATHS], 'stacked-bar')


def review_time_trend(start_date, end_date):
    start, end = date_bounds(start_date, end_date)
    values = {month: [] for month in month_labels(start_date, end_date)}
    decisions = Training.objects.filter(
        OFF_PLATFORM, status__in=(TrainingStatus.ACCEPTED, TrainingStatus.REJECTED),
        process_datetime__gte=start, process_datetime__lt=end,
    ).exclude(citi_verification__auto_approved=True)
    for submitted, decided in decisions.values_list('application_datetime', 'process_datetime').iterator():
        if decided >= submitted:
            values[period(decided)].append((decided - submitted).total_seconds() / 86400)
    rows = [[month, round(median(days), 2) if days else None, percentile(days, 0.9), len(days)]
            for month, days in values.items()]
    report = trend_report(
        'training-review-time', 'Time to review by month',
        'Median and 90th percentile of calendar days from submission to the reviewer\'s decision, by decision '
        'month. Only manual reviews of off-platform trainings that were accepted or rejected are included; '
        'automatic approvals take no review time. Missing medians mean no manual decisions that month. '
        + TRAINING_DESCRIPTION,
        ['Period (YYYY-MM)', 'Median days', '90th percentile days', 'Manual decisions'], rows,
        [('Median days', 1), ('90th percentile days', 2)], start_date, end_date,
    )
    return _style(report, end_date, 'Visible review-time series', ['#2563eb', '#b91c1c'],
                  markers=['circle', 'triangle'])


def type_summary(start_date, end_date):
    start, end = date_bounds(start_date, end_date)
    rows = []
    for row in (Training.objects.filter(OFF_PLATFORM, application_datetime__gte=start, application_datetime__lt=end)
                .order_by().values('training_type__name').annotate(
                    submitted=Count('pk'),
                    accepted=Count('pk', filter=Q(status=TrainingStatus.ACCEPTED)),
                    rejected=Count('pk', filter=Q(status=TrainingStatus.REJECTED)),
                    withdrawn=Count('pk', filter=Q(status=TrainingStatus.WITHDRAWN)),
                    review=Count('pk', filter=Q(status=TrainingStatus.REVIEW)))
                .order_by('-submitted', 'training_type__name')):
        decided = row['accepted'] + row['rejected']
        rows.append([row['training_type__name'], row['submitted'], row['accepted'], row['rejected'],
                     row['withdrawn'], row['review'], round(100 * row['accepted'] / decided, 1) if decided else None])
    return {
        'id': 'training-types', 'title': 'Submissions by training type',
        'description': ('Off-platform submissions in the selected dates by training type, with their outcome today. '
                        'The acceptance rate is accepted divided by accepted plus rejected; withdrawn submissions '
                        'and those awaiting review are left out of it. ' + TRAINING_DESCRIPTION),
        'headers': ['Training type', 'Submitted', 'Accepted', 'Rejected', 'Withdrawn', 'Awaiting review',
                    'Acceptance rate (%)'],
        'rows': rows,
        'chart': {'type': 'horizontal-bar', 'integer': True, 'labels': [row[0] for row in rows],
                  'series': [{'name': 'Submitted', 'values': [row[1] for row in rows], 'color': '#2563eb'},
                             {'name': 'Accepted', 'values': [row[2] for row in rows], 'color': '#15803d'}]},
    }


def review_queue(now=None):
    now = now or timezone.now()
    ages = [(now - submitted).total_seconds() / 86400 for submitted in Training.objects.filter(
        OFF_PLATFORM, status=TrainingStatus.REVIEW, application_datetime__lte=now,
    ).values_list('application_datetime', flat=True)]
    rows = [[label, sum(1 for age in ages if age >= low and (high is None or age < high))]
            for label, low, high in QUEUE_BANDS]
    summary = f'Snapshot: {_stamp(now)}. {len(ages)} trainings awaiting review.'
    if ages:
        summary += f' Median wait {median(ages):.1f} days; oldest {max(ages):.1f} days.'
    return {
        'id': 'training-queue', 'title': 'Trainings awaiting review', 'snapshot': now, 'summary': summary,
        'description': ('Current snapshot of off-platform trainings awaiting review, independent of the selected '
                        'dates, by elapsed days since submission.'),
        'headers': ['Waiting time', 'Trainings'], 'rows': rows,
        'chart': {'type': 'horizontal-bar', 'integer': True, 'legend': False, 'row_height': 40,
                  'labels': [row[0] for row in rows],
                  'series': [{'name': 'Trainings', 'values': [row[1] for row in rows], 'color': '#ea580c'}]},
    }


def _expiry_band(expires, now):
    if expires is None:
        return 'Does not expire'
    days = (expires - now).total_seconds() / 86400
    if days < 0:
        return 'Expired'
    return EXPIRY_BANDS[1 + min(int(days // 30), 3)]


def expiry_summary(now=None):
    """Each active person's latest accepted training of each type, by when it expires."""
    now = now or timezone.now()
    latest = {}
    accepted = Training.objects.filter(status=TrainingStatus.ACCEPTED, user__is_active=True,
                                       process_datetime__isnull=False)
    for user, training_type, name, required, processed, type_duration, course_duration in accepted.values_list(
            'user_id', 'training_type_id', 'training_type__name', 'training_type__required_field',
            'process_datetime', 'training_type__valid_duration', 'course__valid_duration').iterator():
        duration = course_duration if required == RequiredField.PLATFORM else type_duration
        expires = processed + duration if duration else None
        key = (user, training_type)
        if key not in latest or latest[key][1] is not None and (expires is None or expires > latest[key][1]):
            latest[key] = (name, expires)
    by_type = {}
    for name, expires in latest.values():
        by_type.setdefault(name, Counter())[_expiry_band(expires, now)] += 1
    totals = Counter()
    for counts in by_type.values():
        totals.update(counts)
    rows = [[name, *[counts[band] for band in EXPIRY_BANDS]] for name, counts in sorted(by_type.items())]
    return {
        'id': 'training-expiry', 'title': 'Upcoming training expirations', 'snapshot': now,
        'summary': f'Snapshot: {_stamp(now)}. {sum(totals.values())} person–training type pairs.',
        'description': ('Current snapshot, independent of the selected dates. Each active person counts once per '
                        'training type, using their latest accepted training of that type, so renewed trainings '
                        'are not counted as expired. Expiry is the acceptance date plus the validity of the '
                        'training type, or of the course for on-platform trainings, which counts from the course '
                        'start. Bands use 30-day periods.'),
        'headers': ['Training type', *EXPIRY_BANDS], 'rows': rows,
        'chart': {'type': 'horizontal-bar', 'integer': True, 'legend': False, 'row_height': 40,
                  'labels': list(EXPIRY_BANDS),
                  'series': [{'name': 'People', 'values': [totals[band] for band in EXPIRY_BANDS],
                              'color': '#7c3aed'}]},
    }
