from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from project.cloud.access_logs import (DownloadMonthError, close_month, import_day, is_closed, latest_complete_day,
                                       read_s3_logs)
from project.cloud.s3 import create_s3_client


def _local_lines(directory):
    for path in sorted(Path(directory).rglob('*')):
        if path.is_file():
            yield from path.read_text(errors='replace').splitlines()


class Command(BaseCommand):
    help = ('Count dataset downloads from S3 server access logs for UTC days, '
            'or summarize a finished month and delete its per-client rows.')

    def add_arguments(self, parser):
        parser.add_argument('--date', type=date.fromisoformat,
                            help='First UTC day to import (default: the latest day whose logs have all arrived).')
        parser.add_argument('--days', type=int, default=1, help='Number of days to import, starting at --date.')
        parser.add_argument('--bucket', action='append', dest='buckets',
                            help='Data bucket to import or close (default: the configured open, controlled '
                                 'and geo-restricted buckets). Repeat for several buckets.')
        parser.add_argument('--log-dir', help='Read log files from this directory instead of S3.')
        parser.add_argument('--close-month', metavar='YYYY-MM',
                            help='Summarize a finished, fully imported month and delete its per-client rows.')

    def handle(self, *args, **options):
        buckets = options['buckets'] or [bucket for bucket in (
            settings.S3_OPEN_ACCESS_BUCKET, settings.S3_CONTROLLED_ACCESS_BUCKET,
            settings.S3_OPEN_ACCESS_BUCKET_WITH_LOGIN) if bucket]
        if not buckets:
            raise CommandError('No data buckets configured; pass --bucket.')

        if options['close_month']:
            month = date.fromisoformat(options['close_month'] + '-01')
            try:
                counts = close_month(month, buckets)
            except DownloadMonthError as error:
                raise CommandError(str(error))
            versions = {project for project, _ in counts}
            self.stdout.write(f'{month:%Y-%m}: {sum(row["downloads"] for row in counts.values())} downloads '
                              f'of {len(versions)} project versions.')
            return

        if options['days'] < 1:
            raise CommandError('--days must be at least 1.')
        if not options['log_dir'] and not settings.S3_SERVER_ACCESS_LOG_BUCKET:
            raise CommandError('S3_SERVER_ACCESS_LOG_BUCKET is not configured; pass --log-dir.')
        latest = latest_complete_day()
        first = options['date'] or latest
        days = [first + timedelta(days=offset) for offset in range(options['days'])]
        # Check the whole range first, so an import is all or nothing
        if days[-1] > latest:
            raise CommandError(f'Logs for {days[-1]} may still be arriving; the latest day that can be imported '
                               f'is {latest}.')
        closed = sorted({f'{day:%Y-%m}' for day in days if is_closed(day.replace(day=1))})
        if closed:
            raise CommandError(f'Already closed: {", ".join(closed)}.')

        s3 = None if options['log_dir'] else create_s3_client()
        for day in days:
            if options['log_dir']:
                lines = _local_lines(options['log_dir'])
            else:
                lines = (line for bucket in buckets
                         for line in read_s3_logs(s3, settings.S3_SERVER_ACCESS_LOG_BUCKET, bucket, day))
            # On S3, no log files for a day whose logs have all arrived means the bucket had no requests.
            # A local directory may just be the wrong one, so its days stay missing.
            try:
                requests = import_day(day, buckets, lines, record_empty=not options['log_dir'])
            except DownloadMonthError as error:
                raise CommandError(str(error))
            empty = 'no requests' if not options['log_dir'] else 'no log files found'
            self.stdout.write(f'{day}: ' + ', '.join(
                f'{bucket} {count} download requests' if count is not None else f'{bucket} {empty}'
                for bucket, count in requests.items()))
