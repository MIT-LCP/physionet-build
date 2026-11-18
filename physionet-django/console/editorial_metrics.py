"""Editorial metrics: annual figures, monthly time to first decision and the submitted-project queue."""
from collections import OrderedDict
from statistics import median

from django.db.models import Min, Q
from django.urls import reverse
from django.utils import timezone

from console.forms import SUBMISSION_RESPONSE_CHOICES
from console.reporting import date_bounds, median_days, month_labels, period, trend_report
from project.models import ActiveProject, PublishedProject, SubmissionStatus

# Accept, resubmit with revisions and reject; the empty choice is not a decision.
DECISIONS = tuple(value for value, _ in SUBMISSION_RESPONSE_CHOICES if value != '')


def first_decision_durations(start=None, end=None):
    """Yield (first decision, fractional days since submission) once per submitted project version.

    Publishing deletes the active copy, so published and active projects never overlap. Negative
    durations are included for callers to count; start and end bound the first decision date.
    """
    for projects in (PublishedProject.objects.filter(is_legacy=False), ActiveProject.objects.all()):
        observations = projects.filter(submission_datetime__isnull=False).annotate(
            first_decision=Min('edit_logs__decision_datetime', filter=Q(edit_logs__decision__in=DECISIONS)),
        ).filter(first_decision__isnull=False)
        if start is not None:
            observations = observations.filter(first_decision__gte=start, first_decision__lt=end)
        for submitted, decided in observations.values_list('submission_datetime', 'first_decision').iterator(
                chunk_size=1000):
            yield decided, (decided - submitted).total_seconds() / 86400


def editorial_annual_stats(start=None, end=None):
    """Publications use publication dates; first decisions use decision dates."""
    publication_cohort = PublishedProject.objects.filter(is_legacy=False)
    if start is not None:
        publication_cohort = publication_cohort.filter(publish_datetime__gte=start, publish_datetime__lt=end)
    groups = {}

    def group(year):
        return groups.setdefault(year, {'count': 0, 'assignment': [], 'publication': [], 'decision': []})

    for publication, submitted, assigned in publication_cohort.values_list(
            'publish_datetime', 'submission_datetime', 'editor_assignment_datetime').iterator(chunk_size=1000):
        values = group(timezone.localtime(publication).year)
        values['count'] += 1
        if submitted:
            for key, finished in (('assignment', assigned), ('publication', publication)):
                if finished and finished >= submitted:
                    values[key].append((finished - submitted).days)
    for decided, days in first_decision_durations(start, end):
        if days >= 0:
            group(timezone.localtime(decided).year)['decision'].append(days)
    result = OrderedDict()
    for year, values in sorted(groups.items()):
        result[year] = [values['count'],
                        *(median(values[key]) if values[key] else None for key in ('assignment', 'publication')),
                        median_days(values['decision'])]
    return result


def editorial_trend(start_date, end_date):
    start, end = date_bounds(start_date, end_date)
    values = {month: [] for month in month_labels(start_date, end_date)}
    invalid = 0
    for decided, days in first_decision_durations(start, end):
        if days < 0:
            invalid += 1
            continue
        values[period(decided)].append(days)
    rows = [[month, median_days(days), len(days)] for month, days in values.items()]
    return trend_report(
        'editorial-monthly', 'Time to first editorial decision by month',
        'One observation per submitted project version, grouped by first decision month. '
        'Calendar days from initial submission to the earliest recorded accept, revise or reject decision. '
        'Includes active and archived projects and non-legacy publications. '
        'Missing submission or decision dates are omitted. Pending projects do not contribute '
        'to medians. Boundary months may be partial; missing medians mean no valid observations. '
        + (f'Excluded negative durations: {invalid}.' if invalid else ''),
        ['Period (YYYY-MM)', 'Median days to first decision', 'Project versions with a decision'], rows,
        [('Median days to first decision', 1)], start_date, end_date,
        warning=f'Excluded negative durations: {invalid}.' if invalid else '',
    )


def pending_projects(now):
    return ActiveProject.objects.filter(
        submission_status__gt=SubmissionStatus.ARCHIVED, submission_datetime__lte=now,
    ).order_by('submission_datetime', 'pk')


def project_queue_rows(projects, now):
    return [{'label': project.slug,
             'status': project.submission_status_label() + (' (on hold)' if project.is_on_hold else ''),
             'since': project.submission_datetime, 'days': (now - project.submission_datetime).days,
             'url': reverse('submission_info', args=[project.slug])} for project in projects]
