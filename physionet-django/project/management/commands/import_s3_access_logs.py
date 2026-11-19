from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from project.cloud.access_logs import close_month, import_day, read_s3_logs
from project.cloud.s3 import create_s3_client
from project.models import S3DownloadMonth


def _local_lines(directory):
    for path in sorted(Path(directory).rglob('*')):
        if path.is_file():
            yield from path.read_text(errors='replace').splitlines()


class Command(BaseCommand):
    help = ('Count dataset downloads from S3 server access logs for UTC days, '
            'or summarize a finished month and delete its per-client rows.')

    def add_arguments(self, parser):
        parser.add_argument('--date', type=date.fromisoformat,
                            help='UTC day to import (default: yesterday).')
        parser.add_argument('--days', type=int, default=1, help='Number of days to import, starting at --date.')
        parser.add_argument('--bucket', action='append', dest='buckets',
                            help='Data bucket to import (default: the configured open, controlled '
                                 'and geo-restricted buckets). Repeat for several buckets.')
        parser.add_argument('--log-dir', help='Read log files from this directory instead of S3.')
        parser.add_argument('--close-month', metavar='YYYY-MM',
                            help='Summarize a finished month and delete its per-client rows.')

    def handle(self, *args, **options):
        if options['close_month']:
            month = date.fromisoformat(options['close_month'] + '-01')
            if month >= timezone.now().date().replace(day=1):
                raise CommandError('Only finished months can be closed.')
            counts = close_month(month)
            versions = {project for project, _ in counts}
            self.stdout.write(f'{month:%Y-%m}: {sum(row["downloads"] for row in counts.values())} downloads '
                              f'of {len(versions)} project versions.')
            return

        buckets = options['buckets'] or [bucket for bucket in (
            settings.S3_OPEN_ACCESS_BUCKET, settings.S3_CONTROLLED_ACCESS_BUCKET,
            settings.S3_OPEN_ACCESS_BUCKET_WITH_LOGIN) if bucket]
        if not buckets:
            raise CommandError('No data buckets configured; pass --bucket.')
        if not options['log_dir'] and not settings.S3_SERVER_ACCESS_LOG_BUCKET:
            raise CommandError('S3_SERVER_ACCESS_LOG_BUCKET is not configured; pass --log-dir.')
        first = options['date'] or timezone.now().date() - timedelta(days=1)
        s3 = None if options['log_dir'] else create_s3_client()
        for offset in range(options['days']):
            day = first + timedelta(days=offset)
            if S3DownloadMonth.objects.filter(month=day.replace(day=1)).exists():
                raise CommandError(f'{day:%Y-%m} is already closed.')
            if options['log_dir']:
                lines = _local_lines(options['log_dir'])
            else:
                lines = (line for bucket in buckets
                         for line in read_s3_logs(s3, settings.S3_SERVER_ACCESS_LOG_BUCKET, bucket, day))
            requests = import_day(day, buckets, lines)
            self.stdout.write(f'{day}: ' + ', '.join(f'{bucket} {count} download requests'
                                                     for bucket, count in requests.items()))
