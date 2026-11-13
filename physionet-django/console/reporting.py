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
