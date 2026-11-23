"""
Count dataset downloads from S3 server access logs.

Only successful object downloads of published project files and ZIPs
are kept, aggregated per client, project version and UTC day.  IP
addresses, user agents and raw log lines are never stored: anonymous
clients and unmatched AWS principals are reduced to a hash keyed with a
random key for the month, which is deleted when the month is closed.
"""
import hashlib
import hmac
import re
import secrets
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from project.models import (PublishedProject, S3AccessLogImport, S3DownloadClientDay, S3DownloadMonth,
                            S3DownloadMonthStatus)
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

MONTH_COUNTS_CACHE_SECONDS = 300


class DownloadMonthError(ValueError):
    """A day or month that can't be imported or closed."""


def latest_complete_day(now=None):
    """The latest UTC day whose logs have all been delivered."""
    return ((now or timezone.now()) - timedelta(hours=DELIVERY_DELAY_HOURS)).date() - timedelta(days=1)


def _following_month(month):
    return (month + timedelta(days=32)).replace(day=1)


def _month_counts_cache_key(month):
    return f'project:s3-download-counts:{month:%Y-%m}:v1'


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

    # Fetch in batches, so at most `workers` file bodies are held in memory at once
    with ThreadPoolExecutor(workers) as executor:
        for start in range(0, len(keys), workers):
            for text in executor.map(fetch, keys[start:start + workers]):
                yield from text.splitlines()


def _client_hash(key, *parts):
    return hmac.new(key.encode(), '|'.join(parts).encode(), hashlib.sha256).hexdigest()[:32]


def is_closed(month):
    return S3DownloadMonthStatus.objects.filter(month=month, closed_datetime__isnull=False).exists()


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


def import_day(day, buckets, lines, record_empty=False):
    """
    Replace the stored downloads of a UTC day for the given buckets.

    Lines from other buckets or other days are ignored, so the same
    files can be read for consecutive days.  A bucket's earlier rows are
    only replaced if log lines from that day were found for it.  A
    bucket with no log lines is recorded as imported with no requests
    only if record_empty is set: S3 writes no log files for a bucket
    without requests, so once the day's logs have all arrived, no files
    means a quiet day.  Returns the download requests per bucket, or
    None for a bucket with no log lines.
    """
    month = day.replace(day=1)
    stamp = day.strftime('%d/%b/%Y')
    status, _ = S3DownloadMonthStatus.objects.get_or_create(
        month=month, defaults={'hash_key': secrets.token_hex(32)})
    if status.closed_datetime:
        raise DownloadMonthError(f'{month:%Y-%m} is already closed.')
    projects = ProjectIndex()
    users = dict(CloudInformation.objects.filter(aws_user_arn__isnull=False)
                 .values_list('aws_user_arn', 'user_id'))
    totals, requests, seen = {}, dict.fromkeys(buckets, 0), set()
    for line in lines:
        match = LOG_LINE.match(line)
        if not match or match['bucket'] not in requests or not match['time'].startswith(stamp):
            continue
        seen.add(match['bucket'])
        if match['operation'] != 'REST.GET.OBJECT' or match['status'] not in DOWNLOAD_STATUSES:
            continue
        project, is_zip = projects.resolve(match['key'])
        if project is None:
            continue
        requester, user = match['requester'], None
        if requester == '-':
            client = 'anon:' + _client_hash(status.hash_key, match['ip'], match['user_agent'])
        elif requester in users:
            user = users[requester]
            client = f'user:{user}'
        else:
            client = 'aws:' + _client_hash(status.hash_key, requester)
        sent = int(match['bytes_sent']) if match['bytes_sent'].isdigit() else 0
        entry = totals.setdefault((match['bucket'], project, client), [user, 0, 0, 0])
        entry[1] += sent
        entry[2] += sent if is_zip else 0
        entry[3] += 1
        requests[match['bucket']] += 1

    with transaction.atomic():
        # Check again under a lock, in case the month was closed while the lines were being read
        if S3DownloadMonthStatus.objects.select_for_update().get(month=month).closed_datetime:
            raise DownloadMonthError(f'{month:%Y-%m} is already closed.')
        S3DownloadClientDay.objects.filter(date=day, bucket__in=seen).delete()
        S3DownloadClientDay.objects.bulk_create([
            S3DownloadClientDay(date=day, bucket=bucket, project_id=project, client=client, user_id=user,
                                bytes_sent=sent, zip_bytes=zip_bytes, requests=count)
            for (bucket, project, client), (user, sent, zip_bytes, count) in totals.items()
        ], batch_size=1000)
        for bucket in seen:
            S3AccessLogImport.objects.update_or_create(date=day, bucket=bucket,
                                                       defaults={'requests': requests[bucket]})
        if record_empty:
            for bucket in set(buckets) - seen:
                S3AccessLogImport.objects.get_or_create(date=day, bucket=bucket)
    cache.delete(_month_counts_cache_key(month))
    return {bucket: count if bucket in seen else None for bucket, count in requests.items()}


def size_known(main_size, zip_size):
    return max(main_size, zip_size) >= MIN_KNOWN_SIZE


def is_download(sent, zip_bytes, main_size, zip_size):
    if not size_known(main_size, zip_size):
        return False
    if zip_size >= MIN_KNOWN_SIZE and zip_bytes >= ZIP_FRACTION * zip_size:
        return True
    return sent >= DOWNLOAD_FRACTION * max(main_size, zip_size)


def _client_counts(month):
    """
    Counts per (project version, bucket) computed from the month's client rows.

    Each client counts once per version and month: the download
    threshold applies to everything it received from any bucket, and
    the client and its download are attributed to the bucket that sent
    it the most data.  Data transferred and requests stay with the
    bucket that served them.
    """
    rows = (S3DownloadClientDay.objects.filter(date__gte=month, date__lt=_following_month(month))
            .values('project_id', 'client', 'bucket').order_by()
            .annotate(sent=Sum('bytes_sent'), zip_bytes=Sum('zip_bytes'), count=Sum('requests')))
    clients = {}
    for row in rows:
        clients.setdefault((row['project_id'], row['client']), []).append(row)
    sizes = dict((pk, (main, compressed)) for pk, main, compressed in PublishedProject.objects.filter(
        pk__in={project for project, _ in clients}).values_list('pk', 'main_storage_size', 'compressed_storage_size'))
    counts = {}

    def entry(project, bucket):
        return counts.setdefault((project, bucket), {'downloads': 0, 'user_downloads': 0, 'clients': 0,
                                                     'bytes_sent': 0, 'requests': 0})

    for (project, client), buckets in clients.items():
        for row in buckets:
            entry(project, row['bucket'])['bytes_sent'] += row['sent']
            entry(project, row['bucket'])['requests'] += row['count']
        downloaded = is_download(sum(row['sent'] for row in buckets), sum(row['zip_bytes'] for row in buckets),
                                 *sizes[project])
        main = entry(project, min(buckets, key=lambda row: (-row['sent'], row['bucket']))['bucket'])
        main['clients'] += 1
        main['downloads'] += downloaded
        main['user_downloads'] += downloaded and client.startswith('user:')
    return counts


def month_counts(month):
    """
    Counts per (project version, bucket) for the month starting on the given date.

    Closed months are read from S3DownloadMonth.  Open months are
    computed from the client rows and cached briefly.
    """
    if is_closed(month):
        return {(row.project_id, row.bucket): {
            'downloads': row.downloads, 'user_downloads': row.user_downloads, 'clients': row.clients,
            'bytes_sent': row.bytes_sent, 'requests': row.requests}
            for row in S3DownloadMonth.objects.filter(month=month)}
    key = _month_counts_cache_key(month)
    counts = cache.get(key)
    if counts is None:
        counts = _client_counts(month)
        cache.set(key, counts, MONTH_COUNTS_CACHE_SECONDS)
    return counts


def missing_days(month, buckets):
    """The days of the month not yet imported, per bucket."""
    days = [month + timedelta(days=offset) for offset in range((_following_month(month) - month).days)]
    imported = set(S3AccessLogImport.objects.filter(date__gte=month, date__lt=_following_month(month),
                                                    bucket__in=buckets).values_list('bucket', 'date'))
    return {bucket: [day for day in days if (bucket, day) not in imported] for bucket in buckets
            if any((bucket, day) not in imported for day in days)}


def close_month(month, buckets, now=None):
    """
    Keep only the monthly counts, deleting the per-client rows that produced them and the month's hash key.

    Refuses a month that is already closed, whose last day's logs may
    still be arriving, or with days not imported for one of the buckets,
    since its counts could not be rebuilt afterwards.
    """
    if latest_complete_day(now) < _following_month(month) - timedelta(days=1):
        raise DownloadMonthError(f'{month:%Y-%m} can\'t be closed until its last day\'s logs have arrived.')
    missing = missing_days(month, buckets)
    if missing:
        raise DownloadMonthError(f'{month:%Y-%m} has days not imported: ' + '; '.join(
            f'{bucket} {len(days)} days, first {days[0]}' for bucket, days in missing.items()))
    with transaction.atomic():
        status, _ = S3DownloadMonthStatus.objects.select_for_update().get_or_create(month=month)
        if status.closed_datetime:
            raise DownloadMonthError(f'{month:%Y-%m} is already closed.')
        counts = _client_counts(month)
        S3DownloadMonth.objects.bulk_create([S3DownloadMonth(month=month, project_id=project, bucket=bucket, **values)
                                             for (project, bucket), values in counts.items()])
        S3DownloadClientDay.objects.filter(date__gte=month, date__lt=_following_month(month)).delete()
        status.hash_key = ''
        status.closed_datetime = timezone.now()
        status.save()
    cache.delete(_month_counts_cache_key(month))
    return counts
