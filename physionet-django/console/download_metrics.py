"""Dataset downloads counted from S3 server access logs, by whole UTC months."""
from calendar import monthrange
from datetime import date

from django.db.models import Count, Max, Min

from console.reporting import month_labels, partial_periods, trend_report
from project.cloud.access_logs import (DOWNLOAD_FRACTION, MIN_KNOWN_SIZE, latest_complete_day, month_counts,
                                       size_known)
from project.models import PublishedProject, S3AccessLogImport

DOWNLOAD_DESCRIPTION = (
    'Downloads counted from Amazon S3 server access logs of the open, controlled and geo-restricted data buckets. '
    'A download is one client receiving a dataset version in a calendar month (UTC): the whole ZIP file, or at '
    f'least {DOWNLOAD_FRACTION:.0%} of the version\'s recorded size (the larger of its uncompressed and ZIP sizes) '
    'across any of its files and buckets. Versions whose recorded sizes are both under '
    f'{MIN_KNOWN_SIZE // 1_000_000} MB have no reliable size, so their downloads are not counted and only clients '
    'with any file are shown. The same client '
    'counts once per version and month, however many files or retries it needed; a client downloading again in '
    'another month counts again. Registered users are PhysioNet accounts matched through their verified AWS user '
    'ARN; other clients are anonymous, identified by IP address and user agent within the month through a hash '
    'whose random key is deleted when the month is closed, so their counts are estimates (a shared network '
    'counts once, a moving client more than once). Downloads served by '
    'physionet.org rather than redirected to S3, and Google Cloud downloads, are not included.'
)

RANKING_HEADERS = ['Dataset', 'Version', 'Downloads', 'Downloads by registered users', 'Anonymous downloads',
                   'Clients with any file', 'Data transferred (GB)', 'Requests']


def download_record_dates():
    bounds = S3AccessLogImport.objects.aggregate(first=Min('date'), last=Max('date'))
    return {'first': bounds['first'].replace(day=1) if bounds['first'] else None, 'last': bounds['last']}


def _months(start_date, end_date):
    return [date(int(label[:4]), int(label[5:]), 1) for label in month_labels(start_date, end_date)]


def import_coverage(start_date, end_date):
    """
    Imported days per bucket over the whole months containing the selected dates,
    up to the latest day whose logs have all arrived.
    """
    first = start_date.replace(day=1)
    last = min(end_date.replace(day=monthrange(end_date.year, end_date.month)[1]), latest_complete_day())
    if last < first:
        return []
    days = (last - first).days + 1
    rows = (S3AccessLogImport.objects.filter(date__gte=first, date__lte=last)
            .values('bucket').annotate(days=Count('date')).order_by('bucket'))
    return [{'bucket': row['bucket'], 'days': row['days'], 'total': days} for row in rows]


def _add(target, values):
    for key, value in values.items():
        target[key] = target.get(key, 0) + value


def download_report(start_date, end_date):
    months = _months(start_date, end_date)
    monthly, totals, buckets = {}, {}, {}
    for month in months:
        counts = monthly[month.strftime('%Y-%m')] = {}
        for (project, bucket), values in month_counts(month).items():
            _add(counts.setdefault(project, {}), values)
            _add(totals.setdefault(project, {}), values)
            _add(buckets.setdefault(bucket, {}), values)
    labels, known = {}, set()
    for pk, slug, version, main_size, zip_size in PublishedProject.objects.filter(pk__in=totals).values_list(
            'pk', 'slug', 'version', 'main_storage_size', 'compressed_storage_size'):
        labels[pk] = (slug, version)
        if size_known(main_size, zip_size):
            known.add(pk)
    ranking = sorted(totals.items(), key=lambda item: (
        item[0] not in known, -item[1]['downloads'], -item[1]['clients'], labels[item[0]]))
    # Downloads of versions without a reliable size are unknown, not zero.
    rows = [[*labels[project],
             *([values['downloads'], values['user_downloads'], values['downloads'] - values['user_downloads']]
               if project in known else [None, None, None]),
             values['clients'], round(values['bytes_sent'] / 1e9, 2), values['requests']]
            for project, values in ranking]

    top = [project for project, values in ranking[:10] if values['downloads']]
    names = [' / '.join(labels[project]) for project in top]
    partial = partial_periods(list(monthly), months[0], end_date.replace(
        day=monthrange(end_date.year, end_date.month)[1]))
    colors = ['#2563eb', '#ea580c', '#15803d', '#b91c1c', '#7c3aed', '#0e7490', '#a16207', '#be185d',
              '#475569', '#4338ca']
    markers = ['circle', 'square', 'triangle', 'diamond', 'plus', 'cross', 'triangle-down', 'hexagon',
               'pentagon', 'star']
    trend_rows = [[label, *[counts.get(project, {}).get('downloads', 0) for project in top],
                   'Partial month' if limited else 'Full month']
                  for (label, counts), limited in zip(monthly.items(), partial)]
    last = end_date.replace(day=monthrange(end_date.year, end_date.month)[1])
    total_rows = [[label, sum(values['downloads'] for values in counts.values()),
                   sum(1 for values in counts.values() if values['downloads']),
                   round(sum(values['bytes_sent'] for values in counts.values()) / 1e9, 2),
                   sum(values['clients'] for values in counts.values())]
                  for label, counts in monthly.items()]
    downloads_monthly = trend_report(
        'downloads-total-monthly', 'Downloads by month',
        'Downloads of all dataset versions together, each version counted as a separate dataset. '
        + DOWNLOAD_DESCRIPTION,
        ['Period (YYYY-MM)', 'Downloads', 'Dataset versions downloaded'], [row[:3] for row in total_rows],
        [('Downloads', 1)], months[0], last, integer=True)
    volume_monthly = trend_report(
        'downloads-volume-monthly', 'Data transferred by month',
        'Gigabytes sent by S3 for all dataset versions together, including partial downloads and retries. '
        + DOWNLOAD_DESCRIPTION,
        ['Period (YYYY-MM)', 'Data transferred (GB)'], [[row[0], row[3]] for row in total_rows],
        [('Data transferred (GB)', 1)], months[0], last)
    clients_monthly = trend_report(
        'downloads-clients-monthly', 'Clients with any file by month',
        'Clients that received at least one file of a dataset version, whether or not they downloaded enough to '
        'count as a download. A client is counted once per version and month, so a client fetching files from two '
        'versions counts twice; this is not a count of distinct people across the site. ' + DOWNLOAD_DESCRIPTION,
        ['Period (YYYY-MM)', 'Clients with any file'], [[row[0], row[4]] for row in total_rows],
        [('Clients with any file', 1)], months[0], last, integer=True)
    for report, color in ((downloads_monthly, '#2563eb'), (clients_monthly, '#7c3aed'),
                          (volume_monthly, '#0e7490')):
        report['chart'].update({'legend': False, 'period_unit': 'month', 'partial_through': end_date.isoformat()})
        report['chart']['series'][0]['color'] = color
        report['chart']['value_labels'] = True

    bucket_rows = [[bucket, values['downloads'], values['clients'], round(values['bytes_sent'] / 1e9, 2),
                    values['requests']] for bucket, values in sorted(buckets.items())]
    by_bucket = {
        'id': 'downloads-by-bucket', 'title': 'Downloads and data transferred by bucket',
        'description': ('Totals over the selected months for each S3 data bucket. A client that used more than '
                        'one bucket for a version counts, with its download, in the bucket that sent it the most '
                        'data; data transferred and requests stay with the bucket that served them. '
                        + DOWNLOAD_DESCRIPTION),
        'headers': ['Bucket', 'Downloads', 'Clients with any file', 'Data transferred (GB)', 'Requests'],
        'rows': bucket_rows,
        'charts': [
            {'id': 'downloads-bucket-volume', 'title': 'Data transferred by bucket (GB)',
             'chart': {'type': 'horizontal-bar', 'legend': False, 'row_height': 48,
                       'labels': [row[0] for row in bucket_rows],
                       'series': [{'name': 'Data transferred (GB)', 'values': [row[3] for row in bucket_rows],
                                   'color': '#0e7490'}]}},
            {'id': 'downloads-bucket-count', 'title': 'Downloads by bucket',
             'chart': {'type': 'horizontal-bar', 'integer': True, 'legend': False, 'row_height': 48,
                       'labels': [row[0] for row in bucket_rows],
                       'series': [{'name': 'Downloads', 'values': [row[1] for row in bucket_rows],
                                   'color': '#2563eb'}]}},
        ],
    }
    return {
        'downloads_monthly': downloads_monthly, 'clients_monthly': clients_monthly, 'volume_monthly': volume_monthly,
        'by_bucket': by_bucket,
        'ranking': {'id': 'downloads-by-version', 'headers': RANKING_HEADERS, 'rows': rows},
        'trend': {
            'id': 'downloads-monthly', 'title': 'Downloads by dataset version and month',
            'description': ('The ten most downloaded versions over the selected months, with the same versions '
                            'shown in every month. ' + DOWNLOAD_DESCRIPTION),
            'headers': ['Period (YYYY-MM)', *names, 'Period coverage'], 'rows': trend_rows,
            'has_series': bool(top),
            'chart': {'labels': list(monthly), 'partial': partial, 'integer': True, 'period_unit': 'month',
                      'partial_through': end_date.isoformat(), 'interactive_legend': True, 'plot_height': 440,
                      'line_width': 2, 'legend_title': 'Visible dataset versions',
                      'series': [{'name': name, 'period_count': totals[project]['downloads'],
                                  'color': colors[index], 'marker': markers[index],
                                  'values': [row[index + 1] for row in trend_rows]}
                                 for index, (project, name) in enumerate(zip(top, names))]},
        },
    }
