import csv
import tempfile
from datetime import date, datetime, timedelta, timezone as dt_timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from console.download_metrics import download_report, import_coverage
from project.cloud.access_logs import (DownloadMonthError, _month_counts_cache_key, close_month, import_day,
                                       is_download, month_counts, read_s3_logs)
from project.models import (PublishedProject, S3AccessLogImport, S3DownloadClientDay, S3DownloadMonth,
                            S3DownloadMonthStatus)
from user.models import CloudInformation, User

DAY = date(2026, 10, 5)
OCTOBER = date(2026, 10, 1)
ARN = 'arn:aws:iam::123456789012:user/downloader'


def log_line(key, bucket='open-bucket', day=DAY, ip='192.0.2.1', requester='-', operation='REST.GET.OBJECT',
             status='200', sent=100, agent='python-requests/2.32'):
    return (f'owner {bucket} [{day:%d/%b/%Y}:12:00:00 +0000] {ip} {requester} REQ {operation} {key} '
            f'"GET /{key} HTTP/1.1" {status} - {sent} {sent} 10 9 "-" "{agent}" - host SigV4 '
            f'ECDHE-RSA-AES128-GCM-SHA256 AuthHeader {bucket}.s3.amazonaws.com TLSv1.3 - -')


class TestDownloadMetrics(TestCase):
    fixtures = ['demo-user.json', 'site-data.json', 'demo-project.json']

    @classmethod
    def setUpTestData(cls):
        # Tests share the development database, which may already hold imported downloads.
        for model in (S3AccessLogImport, S3DownloadClientDay, S3DownloadMonth, S3DownloadMonthStatus):
            model.objects.all().delete()
        cls.project = PublishedProject.objects.filter(resource_type_id=0).first()
        PublishedProject.objects.filter(pk=cls.project.pk).update(main_storage_size=10_000_000,
                                                                  compressed_storage_size=5_000_000)
        cls.prefix = f'{cls.project.slug}/{cls.project.version}'
        cls.zip_key = f'{cls.project.slug}/{cls.project.slug}-{cls.project.version}.zip'
        cls.user = User.objects.create_user('downloader@example.com', 'password', 'downloader', is_active=True)
        CloudInformation.objects.update_or_create(user=cls.user, defaults={'aws_user_arn': ARN})
        cls.admin = User.objects.get(email='admin@mit.edu')
        cls.admin.user_permissions.add(Permission.objects.get(codename='can_view_stats'))

    def setUp(self):
        for month in (date(2026, 9, 1), OCTOBER, date(2026, 11, 1)):
            cache.delete(_month_counts_cache_key(month))

    def cover_month(self, month=OCTOBER, buckets=('open-bucket',), skip=()):
        """Record every day of the month as imported, except those in skip."""
        day = month
        while day.month == month.month:
            if day not in skip:
                for bucket in buckets:
                    S3AccessLogImport.objects.get_or_create(date=day, bucket=bucket)
            day += timedelta(days=1)

    def test_import_keeps_successful_downloads_of_the_day(self):
        lines = [
            log_line(f'{self.prefix}/RECORDS'),
            log_line(f'{self.prefix}/a%20b.dat', status='206'),
            log_line(f'{self.prefix}/RECORDS', operation='REST.HEAD.OBJECT'),
            log_line(f'{self.prefix}/missing', status='404'),
            log_line(f'{self.prefix}/RECORDS', day=date(2026, 10, 4)),
            log_line(f'{self.prefix}/RECORDS', bucket='other-bucket'),
            log_line('unknown/1.0/file'),
            'not a log line',
        ]
        self.assertEqual(import_day(DAY, ['open-bucket'], lines), {'open-bucket': 2})
        row = S3DownloadClientDay.objects.get()
        self.assertEqual((row.bytes_sent, row.zip_bytes, row.requests, row.user), (200, 0, 2, None))
        self.assertTrue(row.client.startswith('anon:'))
        self.assertNotIn('192.0.2.1', row.client)
        self.assertEqual(S3AccessLogImport.objects.get().requests, 2)

    def test_reimporting_a_day_replaces_its_rows(self):
        lines = [log_line(f'{self.prefix}/RECORDS')]
        import_day(DAY, ['open-bucket'], lines)
        import_day(DAY, ['open-bucket'], lines)
        self.assertEqual(S3DownloadClientDay.objects.get().requests, 1)
        self.assertEqual(S3AccessLogImport.objects.count(), 1)

    def test_clients_count_once_per_month_and_need_a_share_or_the_zip(self):
        import_day(DAY, ['open-bucket', 'controlled-bucket'], [
            log_line(f'{self.prefix}/RECORDS', sent=500_000),
            log_line(f'{self.prefix}/a.dat', ip='192.0.2.2', sent=600_000),
            log_line(f'{self.prefix}/b.dat', bucket='controlled-bucket', requester=ARN, ip='198.51.100.1',
                     sent=400_000),
        ])
        import_day(date(2026, 10, 6), ['open-bucket', 'controlled-bucket'], [
            log_line(f'{self.prefix}/a.dat', ip='192.0.2.2', sent=600_000, day=date(2026, 10, 6)),
            log_line(self.zip_key, bucket='controlled-bucket', requester=ARN, sent=4_800_000, day=date(2026, 10, 6)),
        ])
        counts = month_counts(date(2026, 10, 1))
        # 192.0.2.1 got 5% of the version; 192.0.2.2 got 12% over two days; the user got the whole ZIP.
        self.assertEqual(counts, {
            (self.project.pk, 'open-bucket'): {'downloads': 1, 'user_downloads': 0, 'clients': 2,
                                               'bytes_sent': 1_700_000, 'requests': 3},
            (self.project.pk, 'controlled-bucket'): {'downloads': 1, 'user_downloads': 1, 'clients': 1,
                                                     'bytes_sent': 5_200_000, 'requests': 2},
        })
        self.assertTrue(S3DownloadClientDay.objects.filter(client=f'user:{self.user.pk}', user=self.user).exists())

    def test_versions_without_a_reliable_size_have_unknown_downloads(self):
        PublishedProject.objects.filter(pk=self.project.pk).update(main_storage_size=335_112,
                                                                   compressed_storage_size=0)
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS', sent=200_000)])
        self.assertEqual(month_counts(date(2026, 10, 1))[(self.project.pk, 'open-bucket')]['downloads'], 0)
        row = download_report(date(2026, 10, 1), date(2026, 10, 31))['ranking']['rows'][0]
        self.assertEqual(row[2:6], [None, None, None, 1])

    def test_missing_uncompressed_size_falls_back_to_the_zip_size(self):
        self.assertTrue(is_download(200_000_000, 0, 0, 1_972_995_308))
        self.assertFalse(is_download(100_000_000, 0, 0, 1_972_995_308))

    def test_client_hashes_change_every_month(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS')])
        import_day(date(2026, 11, 5), ['open-bucket'], [log_line(f'{self.prefix}/RECORDS', day=date(2026, 11, 5))])
        self.assertEqual(S3DownloadClientDay.objects.values('client').distinct().count(), 2)

    def test_closing_a_month_keeps_counts_and_deletes_clients_and_key(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS', sent=2_000_000)])
        self.cover_month()
        before = month_counts(OCTOBER)
        close_month(OCTOBER, ['open-bucket'])
        self.assertFalse(S3DownloadClientDay.objects.exists())
        self.assertEqual((S3DownloadMonth.objects.get().downloads, S3DownloadMonth.objects.get().bucket),
                         (1, 'open-bucket'))
        self.assertEqual(month_counts(OCTOBER), before)
        self.assertEqual(S3DownloadMonthStatus.objects.get(month=OCTOBER).hash_key, '')

    def test_closing_a_month_twice_keeps_its_counts(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS', sent=2_000_000)])
        self.cover_month()
        close_month(OCTOBER, ['open-bucket'])
        with self.assertRaisesMessage(DownloadMonthError, 'already closed'):
            close_month(OCTOBER, ['open-bucket'])
        self.assertEqual(month_counts(OCTOBER)[(self.project.pk, 'open-bucket')]['downloads'], 1)

    def test_closing_needs_every_day_imported_and_delivered(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS', sent=2_000_000)])
        self.cover_month(skip=[date(2026, 10, 31)])
        with self.assertRaisesMessage(DownloadMonthError, 'open-bucket 1 days, first 2026-10-31'):
            close_month(OCTOBER, ['open-bucket'])
        self.cover_month()
        # The last day's logs keep arriving until DELIVERY_DELAY_HOURS into the next day
        early = datetime(2026, 11, 1, 3, tzinfo=dt_timezone.utc)
        with self.assertRaisesMessage(DownloadMonthError, 'last day'):
            close_month(OCTOBER, ['open-bucket'], now=early)
        with self.assertRaisesMessage(DownloadMonthError, 'controlled-bucket 31 days'):
            close_month(OCTOBER, ['open-bucket', 'controlled-bucket'])
        self.assertTrue(S3DownloadClientDay.objects.exists())

    def test_day_without_log_lines_is_not_recorded(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS')])
        result = import_day(DAY, ['open-bucket', 'controlled-bucket'], [])
        self.assertEqual(result, {'open-bucket': None, 'controlled-bucket': None})
        # The earlier import of the day is kept, and no coverage is recorded for the empty bucket
        self.assertEqual(S3DownloadClientDay.objects.count(), 1)
        self.assertEqual(list(S3AccessLogImport.objects.values_list('bucket', flat=True)), ['open-bucket'])

    def test_quiet_bucket_is_recorded_when_asked(self):
        result = import_day(DAY, ['open-bucket', 'geo-bucket'], [log_line(f'{self.prefix}/RECORDS')],
                            record_empty=True)
        self.assertEqual(result, {'open-bucket': 1, 'geo-bucket': None})
        self.assertEqual(S3AccessLogImport.objects.get(bucket='geo-bucket', date=DAY).requests, 0)

    def test_import_refuses_a_month_closed_while_reading(self):
        def lines():
            yield log_line(f'{self.prefix}/RECORDS')
            S3DownloadMonthStatus.objects.filter(month=OCTOBER).update(closed_datetime=datetime.now(dt_timezone.utc))

        with self.assertRaisesMessage(DownloadMonthError, 'already closed'):
            import_day(DAY, ['open-bucket'], lines())
        self.assertFalse(S3DownloadClientDay.objects.exists())
        self.assertFalse(S3AccessLogImport.objects.exists())

    def test_threshold_applies_across_buckets(self):
        # 6% from each bucket: one download, attributed to the bucket that sent the most
        import_day(DAY, ['open-bucket', 'controlled-bucket'], [
            log_line(f'{self.prefix}/a.dat', sent=600_000),
            log_line(f'{self.prefix}/b.dat', bucket='controlled-bucket', sent=650_000),
        ])
        self.assertEqual(month_counts(OCTOBER), {
            (self.project.pk, 'open-bucket'): {'downloads': 0, 'user_downloads': 0, 'clients': 0,
                                               'bytes_sent': 600_000, 'requests': 1},
            (self.project.pk, 'controlled-bucket'): {'downloads': 1, 'user_downloads': 0, 'clients': 1,
                                                     'bytes_sent': 650_000, 'requests': 1},
        })

    def test_open_month_counts_are_cached(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS', sent=2_000_000)])
        month_counts(OCTOBER)
        with self.assertNumQueries(1):
            month_counts(OCTOBER)

    def test_s3_logs_are_fetched_in_batches(self):
        class FakeS3:
            def __init__(self):
                self.fetched = 0

            def get_paginator(self, name):
                return self

            def paginate(self, Bucket, Prefix):
                if Prefix != f'open-bucket/logs/{DAY}-':
                    return []
                return [{'Contents': [{'Key': f'{Prefix}{i}'} for i in range(10)]}]

            def get_object(self, Bucket, Key):
                self.fetched += 1
                return {'Body': type('Body', (), {'read': lambda body: b'line\n'})()}

        s3 = FakeS3()
        lines = read_s3_logs(s3, 'logs', 'open-bucket', DAY, workers=2)
        next(lines)
        self.assertLessEqual(s3.fetched, 2)
        self.assertEqual(len(list(lines)), 9)

    def test_coverage_stops_at_the_latest_complete_day(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS')])
        with patch('console.download_metrics.latest_complete_day', return_value=date(2026, 10, 10)):
            self.assertEqual(import_coverage(OCTOBER, date(2026, 10, 31)),
                             [{'bucket': 'open-bucket', 'days': 1, 'total': 10}])

    def test_report_ranks_versions_by_downloads(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS', sent=2_000_000)])
        report = download_report(date(2026, 9, 15), date(2026, 10, 31))
        self.assertEqual(report['ranking']['rows'],
                         [[self.project.slug, self.project.version, 1, 0, 1, 1, 0.0, 1]])
        self.assertEqual(report['trend']['rows'], [['2026-09', 0, 'Full month'], ['2026-10', 1, 'Full month']])

    def test_report_totals_by_month_and_bucket(self):
        import_day(DAY, ['open-bucket', 'controlled-bucket'], [
            log_line(f'{self.prefix}/RECORDS', sent=2_000_000),
            log_line(f'{self.prefix}/RECORDS', ip='192.0.2.9', sent=100),
            log_line(f'{self.prefix}/b.dat', bucket='controlled-bucket', requester=ARN, sent=3_000_000_000),
        ])
        report = download_report(date(2026, 9, 1), date(2026, 10, 31))
        self.assertEqual([row[:3] for row in report['downloads_monthly']['rows']],
                         [['2026-09', 0, 0], ['2026-10', 2, 1]])
        self.assertEqual([row[:2] for row in report['volume_monthly']['rows']], [['2026-09', 0.0], ['2026-10', 3.0]])
        self.assertEqual([row[:2] for row in report['clients_monthly']['rows']], [['2026-09', 0], ['2026-10', 3]])
        self.assertEqual(report['by_bucket']['rows'], [['controlled-bucket', 1, 1, 3.0, 1],
                                                       ['open-bucket', 1, 2, 0.0, 2]])
        self.assertEqual(report['by_bucket']['charts'][1]['chart']['series'][0]['values'], [1, 1])

    def test_page_and_csv_exports(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS', sent=2_000_000)])
        self.client.force_login(self.admin)
        url = reverse('download_stats')
        dates = {'start_date': '2026-10-01', 'end_date': '2026-10-31'}
        response = self.client.get(url, dates)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Most downloaded dataset versions')
        self.assertContains(response, 'open-bucket 1 of 31')
        rows = list(csv.reader(StringIO(self.client.get(url, {**dates, 'export': 'csv'}).content.decode())))
        self.assertEqual(rows[1][:3], [self.project.slug, self.project.version, '1'])
        for export in ('monthly', 'total-monthly', 'clients-monthly'):
            rows = list(csv.reader(StringIO(self.client.get(url, {**dates, 'export': export}).content.decode())))
            self.assertEqual(rows[1][:2], ['2026-10', '1'])
        rows = list(csv.reader(StringIO(self.client.get(url, {**dates, 'export': 'volume-monthly'}).content.decode())))
        self.assertEqual(rows[0][:2], ['Period (YYYY-MM)', 'Data transferred (GB)'])
        rows = list(csv.reader(StringIO(self.client.get(url, {**dates, 'export': 'buckets'}).content.decode())))
        self.assertEqual(rows[1][:2], ['open-bucket', '1'])
        for title in ('Downloads by month', 'Clients with any file by month', 'Data transferred by month',
                      'Downloads and data transferred by bucket'):
            self.assertContains(response, title)

    def test_page_requires_stats_permission(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('download_stats')).status_code, 403)

    def test_command_imports_local_logs_and_refuses_closed_months(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, '2026-10-05-12-00-00-ABC').write_text(log_line(f'{self.prefix}/RECORDS') + '\n')
            out = StringIO()
            call_command('import_s3_access_logs', '--date', '2026-10-05', '--bucket', 'open-bucket',
                         '--log-dir', directory, stdout=out)
            self.assertIn('open-bucket 1 download requests', out.getvalue())
            self.cover_month()
            call_command('import_s3_access_logs', '--close-month', '2026-10', '--bucket', 'open-bucket',
                         stdout=StringIO())
            with self.assertRaisesMessage(CommandError, 'already closed'):
                call_command('import_s3_access_logs', '--close-month', '2026-10', '--bucket', 'open-bucket')
            # A range reaching a closed month is refused before anything is imported
            with self.assertRaisesMessage(CommandError, 'Already closed: 2026-10'):
                call_command('import_s3_access_logs', '--date', '2026-09-30', '--days', '2',
                             '--bucket', 'open-bucket', '--log-dir', directory)
            self.assertFalse(S3AccessLogImport.objects.filter(date=date(2026, 9, 30)).exists())

    def test_command_records_quiet_buckets_from_s3_only(self):
        command = 'project.management.commands.import_s3_access_logs'
        with self.settings(S3_SERVER_ACCESS_LOG_BUCKET='logs'), \
                patch(f'{command}.create_s3_client'), patch(f'{command}.read_s3_logs', return_value=[]):
            out = StringIO()
            call_command('import_s3_access_logs', '--date', '2026-10-05', '--bucket', 'geo-bucket', stdout=out)
        self.assertIn('geo-bucket no requests', out.getvalue())
        self.assertTrue(S3AccessLogImport.objects.filter(date=DAY, bucket='geo-bucket').exists())
        with tempfile.TemporaryDirectory() as directory:
            call_command('import_s3_access_logs', '--date', '2026-10-06', '--bucket', 'geo-bucket',
                         '--log-dir', directory, stdout=StringIO())
        self.assertFalse(S3AccessLogImport.objects.filter(date=date(2026, 10, 6)).exists())

    def test_command_rejects_bad_ranges(self):
        with self.assertRaisesMessage(CommandError, 'at least 1'):
            call_command('import_s3_access_logs', '--days', '0', '--bucket', 'open-bucket', '--log-dir', '.')
        with patch('project.management.commands.import_s3_access_logs.latest_complete_day',
                   return_value=date(2026, 10, 30)):
            with self.assertRaisesMessage(CommandError, 'may still be arriving'):
                call_command('import_s3_access_logs', '--date', '2026-10-30', '--days', '2',
                             '--bucket', 'open-bucket', '--log-dir', '.')
