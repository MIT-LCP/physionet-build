import csv
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from console.download_metrics import download_report
from project.cloud.access_logs import close_month, import_day, is_download, month_counts
from project.models import PublishedProject, S3AccessLogImport, S3DownloadClientDay, S3DownloadMonth
from user.models import CloudInformation, User

DAY = date(2026, 10, 5)
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
        for model in (S3AccessLogImport, S3DownloadClientDay, S3DownloadMonth):
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

    def test_closing_a_month_keeps_counts_and_deletes_clients(self):
        import_day(DAY, ['open-bucket'], [log_line(f'{self.prefix}/RECORDS', sent=2_000_000)])
        before = month_counts(date(2026, 10, 1))
        close_month(date(2026, 10, 1))
        self.assertFalse(S3DownloadClientDay.objects.exists())
        self.assertEqual((S3DownloadMonth.objects.get().downloads, S3DownloadMonth.objects.get().bucket),
                         (1, 'open-bucket'))
        self.assertEqual(month_counts(date(2026, 10, 1)), before)

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
        self.assertNotEqual(self.client.get(reverse('download_stats')).status_code, 200)

    def test_command_imports_local_logs_and_refuses_closed_months(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, '2026-10-05-12-00-00-ABC').write_text(log_line(f'{self.prefix}/RECORDS') + '\n')
            out = StringIO()
            call_command('import_s3_access_logs', '--date', '2026-10-05', '--bucket', 'open-bucket',
                         '--log-dir', directory, stdout=out)
            self.assertIn('open-bucket 1 download requests', out.getvalue())
            call_command('import_s3_access_logs', '--close-month', '2026-10', stdout=StringIO())
            with self.assertRaises(CommandError):
                call_command('import_s3_access_logs', '--date', '2026-10-05', '--bucket', 'open-bucket',
                             '--log-dir', directory)
