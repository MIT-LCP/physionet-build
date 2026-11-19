"""
Count dataset downloads from S3 server access logs.

Only successful object downloads of published project files and ZIPs
are kept, aggregated per client, project version and UTC day.  IP
addresses, user agents and raw log lines are never stored: anonymous
clients and unmatched AWS principals are reduced to a keyed hash that
changes every month.
"""
import hashlib
import hmac
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.db import transaction

from project.models import PublishedProject, S3AccessLogImport, S3DownloadClientDay, S3DownloadMonth
from user.models import CloudInformation

LOG_LINE = re.compile(
    r'\S+ (?P<bucket>\S+) \[(?P<time>[^\]]+)\] (?P<ip>\S+) (?P<requester>\S+) \S+ (?P<operation>\S+) '
    r'(?P<key>\S+) "[^"]*" (?P<status>\d{3}) \S+ (?P<bytes_sent>\S+) \S+ \S+ \S+ "[^"]*" "(?P<user_agent>[^"]*)"'
)
DOWNLOAD_STATUSES = ('200', '206')

# A client downloaded a version in a month if it received the whole ZIP,
# or at least this fraction of the version's uncompressed size.
DOWNLOAD_FRACTION = 0.1
ZIP_FRACTION = 0.9
# Some versions have missing or implausibly small recorded sizes, which
# would turn any file into a download; they are not counted.
MIN_KNOWN_SIZE = 1_000_000

# Logs are delivered with a delay, so a day's events also appear in the
# files named after the first hours of the next day.
DELIVERY_DELAY_HOURS = 6


def log_prefixes(bucket, day):
    following = day + timedelta(days=1)
    return [f'{bucket}/logs/{day.isoformat()}-',
            *(f'{bucket}/logs/{following.isoformat()}-{hour:02d}-' for hour in range(DELIVERY_DELAY_HOURS))]


def read_s3_logs(s3, log_bucket, bucket, day, workers=32):
    """Yield the lines of the log files that may contain events from the day."""
    keys = []
    paginator = s3.get_paginator('list_objects_v2')
    for prefix in log_prefixes(bucket, day):
        for page in paginator.paginate(Bucket=log_bucket, Prefix=prefix):
            keys.extend(item['Key'] for item in page.get('Contents', []))

    def fetch(key):
        return s3.get_object(Bucket=log_bucket, Key=key)['Body'].read().decode('utf-8', 'replace')

    with ThreadPoolExecutor(workers) as executor:
        for text in executor.map(fetch, keys):
            yield from text.splitlines()


def _client_hash(month, *parts):
    message = '|'.join([month, *parts]).encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()[:32]


class ProjectIndex:
    """Map S3 object keys to published project versions."""

    def __init__(self):
        self.versions, self.zips = {}, {}
        for pk, slug, version in PublishedProject.objects.values_list('pk', 'slug', 'version'):
            self.versions[(slug, version)] = pk
            self.zips[(slug, f'{slug}-{version}.zip')] = pk

    def resolve(self, key):
        """Return (project id, whether the key is the project's ZIP), or (None, False)."""
        parts = urllib.parse.unquote(key).split('/')
        if len(parts) > 2:
            return self.versions.get((parts[0], parts[1])), False
        if len(parts) == 2 and (parts[0], parts[1]) in self.zips:
            return self.zips[(parts[0], parts[1])], True
        return None, False


def import_day(day, buckets, lines):
    """
    Replace the stored downloads of a UTC day for the given buckets.

    Lines from other buckets or other days are ignored, so the same
    files can be read for consecutive days.
    """
    stamp, month = day.strftime('%d/%b/%Y'), day.strftime('%Y-%m')
    projects = ProjectIndex()
    users = dict(CloudInformation.objects.filter(aws_user_arn__isnull=False)
                 .values_list('aws_user_arn', 'user_id'))
    totals, requests = {}, dict.fromkeys(buckets, 0)
    for line in lines:
        match = LOG_LINE.match(line)
        if (not match or match['bucket'] not in requests or not match['time'].startswith(stamp)
                or match['operation'] != 'REST.GET.OBJECT' or match['status'] not in DOWNLOAD_STATUSES):
            continue
        project, is_zip = projects.resolve(match['key'])
        if project is None:
            continue
        requester, user = match['requester'], None
        if requester == '-':
            client = 'anon:' + _client_hash(month, match['ip'], match['user_agent'])
        elif requester in users:
            user = users[requester]
            client = f'user:{user}'
        else:
            client = 'aws:' + _client_hash(month, requester)
        sent = int(match['bytes_sent']) if match['bytes_sent'].isdigit() else 0
        entry = totals.setdefault((match['bucket'], project, client), [user, 0, 0, 0])
        entry[1] += sent
        entry[2] += sent if is_zip else 0
        entry[3] += 1
        requests[match['bucket']] += 1

    with transaction.atomic():
        S3DownloadClientDay.objects.filter(date=day, bucket__in=buckets).delete()
        S3DownloadClientDay.objects.bulk_create([
            S3DownloadClientDay(date=day, bucket=bucket, project_id=project, client=client, user_id=user,
                                bytes_sent=sent, zip_bytes=zip_bytes, requests=count)
            for (bucket, project, client), (user, sent, zip_bytes, count) in totals.items()
        ], batch_size=1000)
        for bucket, count in requests.items():
            S3AccessLogImport.objects.update_or_create(date=day, bucket=bucket, defaults={'requests': count})
    return requests


def size_known(main_size, zip_size):
    return max(main_size, zip_size) >= MIN_KNOWN_SIZE


def is_download(sent, zip_bytes, main_size, zip_size):
    if not size_known(main_size, zip_size):
        return False
    if zip_size >= MIN_KNOWN_SIZE and zip_bytes >= ZIP_FRACTION * zip_size:
        return True
    return sent >= DOWNLOAD_FRACTION * max(main_size, zip_size)


def month_counts(month):
    """
    Counts per (project version, bucket) for the month starting on the given date.

    Each client counts once per version, bucket and month.  A download
    requires the ZIP or a minimum share of the version; clients count
    any file.
    """
    summary = S3DownloadMonth.objects.filter(month=month)
    if summary.exists():
        return {(row.project_id, row.bucket): {
            'downloads': row.downloads, 'user_downloads': row.user_downloads, 'clients': row.clients,
            'bytes_sent': row.bytes_sent, 'requests': row.requests} for row in summary}
    following = (month + timedelta(days=32)).replace(day=1)
    clients = {}
    rows = S3DownloadClientDay.objects.filter(date__gte=month, date__lt=following).values_list(
        'project_id', 'bucket', 'client', 'bytes_sent', 'zip_bytes', 'requests')
    for project, bucket, client, sent, zip_bytes, count in rows:
        entry = clients.setdefault((project, bucket, client), [0, 0, 0])
        entry[0] += sent
        entry[1] += zip_bytes
        entry[2] += count
    sizes = dict((pk, (main, compressed)) for pk, main, compressed in PublishedProject.objects.filter(
        pk__in={key[0] for key in clients}).values_list('pk', 'main_storage_size', 'compressed_storage_size'))
    counts = {}
    for (project, bucket, client), (sent, zip_bytes, count) in clients.items():
        row = counts.setdefault((project, bucket), {'downloads': 0, 'user_downloads': 0, 'clients': 0,
                                                    'bytes_sent': 0, 'requests': 0})
        downloaded = is_download(sent, zip_bytes, *sizes[project])
        row['downloads'] += downloaded
        row['user_downloads'] += downloaded and client.startswith('user:')
        row['clients'] += 1
        row['bytes_sent'] += sent
        row['requests'] += count
    return counts


def close_month(month):
    """Keep only the monthly counts, deleting the per-client rows that produced them."""
    following = (month + timedelta(days=32)).replace(day=1)
    with transaction.atomic():
        S3DownloadMonth.objects.filter(month=month).delete()
        counts = month_counts(month)
        S3DownloadMonth.objects.bulk_create([S3DownloadMonth(month=month, project_id=project, bucket=bucket, **values)
                                             for (project, bucket), values in counts.items()])
        S3DownloadClientDay.objects.filter(date__gte=month, date__lt=following).delete()
    return counts
