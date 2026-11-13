"""Definitions shared by monthly operational reports and their CSV exports."""
import csv
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


def trend_report(identifier, title, description, headers, rows, series):
    return {'id': identifier, 'title': title, 'description': description,
            'headers': headers, 'rows': rows,
            'chart': {'labels': [row[0] for row in rows], 'series': [
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
        [('Requests submitted', 1), ('Approvals', 2), ('Rejections', 3)],
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


def queue_csv(identifier, rows):
    return report_csv({'id': identifier, 'headers': ['Project or application', 'Status', 'Since', 'Elapsed days'],
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
    return trend_report(
        'credentialing-monthly', 'Credentialing decision time by month',
        'Grouped by decision date, measuring calendar days from application to decision. '
        'Accepted includes later-revoked credentials. Withdrawals and pending applications are excluded. '
        'Missing medians mean no valid observations; boundary months may be partial. '
        f'Excluded negative durations: {invalid}.',
        ['Period (YYYY-MM)', 'Accepted median days', 'Accepted decisions', 'Rejected median days', 'Rejected decisions'],
        rows, [('Accepted median days', 1), ('Rejected median days', 3)],
    )


def pending_credentials(now):
    from user.models import CredentialApplication
    return CredentialApplication.objects.filter(
        status=CredentialApplication.Status.PENDING, application_datetime__lte=now,
    ).order_by('application_datetime', 'pk')


def credential_queue_rows(applications, now):
    from django.urls import reverse
    rows = []
    for app in applications:
        if app.reference_contact_datetime is None:
            status = 'Awaiting reference contact'
        elif app.reference_response_datetime is None:
            status = 'Awaiting reference response'
        else:
            status = 'Awaiting processing after reference response'
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
    return {'id': 'repeated-credentialing', 'headers': ['Username', 'Applications', 'Accepted (including revoked)',
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
        f'Excluded negative durations: {invalid}.',
        ['Period (YYYY-MM)', 'Median days to first decision', 'Project versions with a decision'], rows,
        [('Median days to first decision', 1)],
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
