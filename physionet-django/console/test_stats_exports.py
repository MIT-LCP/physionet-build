import csv
from html.parser import HTMLParser
from io import StringIO

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
        self.assertContains(page, 'class="btn btn-primary">Export data</a>')
        parser = StatsTableParser()
        parser.feed(page.content.decode())
        expected = parser.tables[table_index]
        year = None
        for row in expected[1:]:
            # The monthly HTML table displays each year only once.
            year = row[0] or year
            row[0] = year
            row[:] = ['' if cell == 'None' else cell for cell in row]

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
        rows = self.assert_export_matches_table(
            'submission_stats', 'submission-monthly-stats.csv', table='monthly',
        )
        self.assertEqual(len(rows), 19)
        self.assertTrue(all(row[0] for row in rows[1:]))

    def test_submission_yearly_export_matches_all_six_years(self):
        rows = self.assert_export_matches_table(
            'submission_stats', 'submission-yearly-stats.csv', table_index=1, table='yearly',
        )
        self.assertEqual(len(rows), 7)

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
