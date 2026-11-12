import csv
from datetime import datetime
from html.parser import HTMLParser
from io import StringIO
from unittest import mock
from urllib.parse import urlencode

from django.test import TestCase
from django.urls import reverse

from user.models import User


class StatsTableParser(HTMLParser):
    """Read table cells to compare downloads with the displayed statistics."""

    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.table = []
        elif tag == 'tr' and self.table is not None:
            self.row = []
        elif tag in ('th', 'td') and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('th', 'td') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None


class TestStatsExports(TestCase):
    fixtures = [
        'demo-training-type.json', 'demo-user.json', 'site-data.json', 'demo-project.json',
    ]

    def setUp(self):
        self.client.force_login(User.objects.get(email='admin@mit.edu'))

    def assert_export_matches_table(self, view, filename, table_index=0, **params):
        url = reverse(view)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        query = urlencode({'export': 'csv', **params}).replace('&', '&amp;')
        self.assertContains(page, f'href="{url}?{query}"')
        parser = StatsTableParser()
        parser.feed(page.content.decode())
        expected = parser.tables[table_index]
        year = None
        for row in expected[1:]:
            # The monthly HTML table displays each year only once.
            year = row[0] or year
            row[0] = year
            row[:] = ['' if cell == 'None' else cell for cell in row]

        if params.get('table') == 'monthly':
            expected[0].insert(0, 'Period (YYYY-MM)')
            for row in expected[1:]:
                period = datetime.strptime(f'{row[0]}-{row[1]}', '%Y-%B').strftime('%Y-%m')
                row.insert(0, period)
        expected = [expected[0], *sorted(expected[1:], key=lambda row: row[0])]

        response = self.client.get(url, {'export': 'csv', **params})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertEqual(response['Content-Disposition'], f'attachment; filename="{filename}"')
        actual = list(csv.reader(StringIO(response.content.decode())))
        self.assertEqual(actual, expected)
        return actual

    def test_credentialing_export_matches_displayed_metrics(self):
        rows = self.assert_export_matches_table('credentialing_stats', 'credentialing-stats.csv')
        self.assertGreater(len(rows), 1)

    def test_editorial_export_matches_displayed_metrics(self):
        rows = self.assert_export_matches_table('editorial_stats', 'editorial-stats.csv')
        self.assertGreater(len(rows), 1)

    def test_submission_monthly_export_matches_all_18_months(self):
        # January exercises the year boundary in the rolling window.
        with mock.patch('console.views.datetime', wraps=datetime) as clock:
            clock.today.return_value = datetime(2026, 1, 15)
            rows = self.assert_export_matches_table(
                'submission_stats', 'submission-monthly-stats-2026-01-15.csv', table='monthly',
            )
        self.assertEqual(len(rows), 19)
        self.assertTrue(all(row[0] for row in rows[1:]))
        self.assertEqual(rows[1][0], '2024-08')
        self.assertEqual(rows[-1][0], '2026-01')
        self.assertEqual([row[0] for row in rows[1:]], sorted(row[0] for row in rows[1:]))

    def test_submission_yearly_export_matches_all_six_years(self):
        with mock.patch('console.views.datetime', wraps=datetime) as clock:
            clock.today.return_value = datetime(2026, 1, 15)
            rows = self.assert_export_matches_table(
                'submission_stats', 'submission-yearly-stats-2026-01-15.csv', table_index=1, table='yearly',
            )
        self.assertEqual(len(rows), 7)

    def test_monthly_is_the_explicit_default_export(self):
        url = reverse('submission_stats')
        default = self.client.get(url, {'export': 'csv'})
        monthly = self.client.get(url, {'export': 'csv', 'table': 'monthly'})
        self.assertEqual(default.status_code, 200)
        self.assertEqual(default.content, monthly.content)
        self.assertEqual(default['Content-Disposition'], monthly['Content-Disposition'])

    def test_unknown_export_table_returns_404(self):
        for table in ('daily', 'yearley', ''):
            with self.subTest(table=table):
                response = self.client.get(reverse('submission_stats'), {'export': 'csv', 'table': table})
                self.assertEqual(response.status_code, 404)
                self.assertNotIn('Content-Disposition', response)

    def test_submission_tables_remain_newest_first(self):
        page = self.client.get(reverse('submission_stats'))
        for name in ('stats', 'yearly_stats'):
            years = list(page.context[name])
            self.assertEqual(years, sorted(years, reverse=True))

    def test_exports_require_stats_permission(self):
        user = User.objects.create_user(
            email='stats-export-test@example.com', username='stats-export-test',
            password='test-password', is_active=True,
        )
        self.client.force_login(user)
        for view, params in (
            ('credentialing_stats', {}), ('editorial_stats', {}),
            ('submission_stats', {'table': 'monthly'}), ('submission_stats', {'table': 'yearly'}),
        ):
            with self.subTest(view=view, params=params):
                response = self.client.get(reverse(view), {'export': 'csv', **params})
                self.assertEqual(response.status_code, 403)

    def test_anonymous_users_cannot_export(self):
        self.client.logout()
        for view in ('credentialing_stats', 'editorial_stats', 'submission_stats'):
            with self.subTest(view=view):
                response = self.client.get(reverse(view), {'export': 'csv'})
                self.assertEqual(response.status_code, 403)
