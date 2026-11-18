import csv
from datetime import date, datetime, timezone as dt_timezone
from html.parser import HTMLParser
from io import StringIO
from unittest import mock
from urllib.parse import urlencode

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from console.credential_metrics import ANNUAL_STATS_CACHE_KEY
from user.models import User


class StatsTableParser(HTMLParser):
    """Read table cells to compare downloads with the displayed statistics."""

    def __init__(self):
        super().__init__()
        self.tables = []
        self.tables_by_id = {}
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.table = []
            self.table_id = dict(attrs).get('id')
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
            if self.table_id:
                self.tables_by_id[self.table_id] = self.table
            self.table = None


class TestStatsExports(TestCase):
    fixtures = [
        'demo-training-type.json', 'demo-user.json', 'site-data.json', 'demo-project.json',
    ]

    def setUp(self):
        cache.delete(ANNUAL_STATS_CACHE_KEY)
        self.client.force_login(User.objects.get(email='admin@mit.edu'))

    def assert_export_matches_table(self, view, filename, table_index=0, table_id=None, **params):
        url = reverse(view)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        query = urlencode({'export': 'csv', **params}).replace('&', '&amp;')
        self.assertContains(page, f'href="{url}?{query}"')
        parser = StatsTableParser()
        parser.feed(page.content.decode())
        expected = parser.tables_by_id[table_id] if table_id else parser.tables[table_index]
        year = None
        partial_rows = []
        for row in expected[1:]:
            partial_rows.append(any(cell.endswith('*') for cell in row))
            # The monthly HTML table displays each year only once.
            year = row[0] or year
            row[0] = year
            row[:] = ['' if cell == 'None' else cell.rstrip('*') for cell in row]

        if params.get('table') == 'monthly':
            expected[0].insert(0, 'Period (YYYY-MM)')
            for row in expected[1:]:
                period = datetime.strptime(f'{row[0]}-{row[1]}', '%Y-%B').strftime('%Y-%m')
                row.insert(0, period)
        if view == 'submission_stats':
            expected[0].append('Period coverage')
            unit = 'month' if params.get('table') == 'monthly' else 'year'
            for row, partial in zip(expected[1:], partial_rows):
                row.append(f'{"Partial" if partial else "Full"} {unit}')
        expected = [expected[0], *sorted(expected[1:], key=lambda row: row[0])]

        response = self.client.get(url, {'export': 'csv', **params})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertEqual(response['Content-Disposition'], f'attachment; filename="{filename}"')
        actual = list(csv.reader(StringIO(response.content.decode())))
        self.assertEqual(actual, expected)
        return actual

    def test_credentialing_export_matches_displayed_metrics(self):
        url = reverse('credentialing_stats')
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'href="?export=annual"')
        response = self.client.get(url, {'export': 'annual'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="credentialing-annual-'))
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        parser = StatsTableParser()
        parser.feed(page.content.decode())
        outcomes = parser.tables_by_id['annual-outcomes'][1:]
        self.assertGreater(len(rows), 0)
        self.assertEqual(len(rows), len(outcomes))
        for exported, displayed in zip(rows, outcomes):
            self.assertEqual(list(exported.values())[:7], displayed[:7])
            values = page.context['stats'][int(exported['Application year'])]
            for header, key in (
                ('Decision median days', 'time_to_decision'),
                ('Valid decision durations', 'decision_observations'),
                ('Contact median days', 'time_to_ref'),
                ('Valid contact durations', 'contact_observations'),
                ('Response median hours', 'time_to_reply'),
                ('Valid response durations', 'response_observations'),
            ):
                self.assertEqual(exported[header], '' if values[key] is None else str(values[key]))

    def test_credentialing_csv_keeps_the_original_seven_columns(self):
        url = reverse('credentialing_stats')
        response = self.client.get(url, {'export': 'csv'})
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="credentialing-stats.csv"')
        rows = list(csv.reader(StringIO(response.content.decode())))
        self.assertEqual(rows[0], [
            'Year', 'Total applications', 'Total handled (accepted + revoked + rejected)', 'Approved (%)',
            'Decision time (days, median)', 'Time to contact reference (days, median)',
            'Reference response time (hours, median)'])
        stats = self.client.get(url).context['stats']
        self.assertEqual(len(rows) - 1, len(stats))
        for row in rows[1:]:
            values = stats[int(row[0])]
            for cell, key in zip(row[1:], ('count', 'processed', 'approved', 'time_to_decision',
                                           'time_to_ref', 'time_to_reply')):
                self.assertEqual(cell, '' if values[key] is None else str(values[key]))

    def test_editorial_export_matches_displayed_metrics(self):
        url = reverse('editorial_stats')
        page = self.client.get(url)
        self.assertContains(page, f'href="{url}?export=csv"')
        parser = StatsTableParser()
        parser.feed(page.content.decode())
        header, *displayed = parser.tables_by_id['editorial-annual']
        displayed = [['' if cell == 'None' else cell for cell in row] for row in displayed]
        response = self.client.get(url, {'export': 'csv'})
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="editorial-stats.csv"')
        exported_header, *exported = list(csv.reader(StringIO(response.content.decode())))
        self.assertEqual(exported_header, header)
        # The table shows five years per page, newest first; the CSV has every year.
        self.assertEqual(len(exported), page.context['review_page'].paginator.count)
        self.assertGreater(len(exported), 1)
        self.assertEqual(displayed, list(reversed(exported))[:len(displayed)])

    def test_submission_monthly_export_matches_all_18_months(self):
        # January exercises the year boundary in the rolling window.
        with mock.patch('console.views.timezone.localdate', return_value=date(2026, 1, 15)):
            rows = self.assert_export_matches_table(
                'submission_stats', 'submission-monthly-stats-2026-01-15.csv', table='monthly',
                table_id='submission-monthly-activity-table',
            )
        self.assertEqual(len(rows), 19)
        self.assertTrue(all(row[0] for row in rows[1:]))
        self.assertEqual(rows[1][0], '2024-08')
        self.assertEqual(rows[-1][0], '2026-01')
        self.assertEqual(rows[-1][-1], 'Partial month')
        self.assertTrue(all(row[-1] == 'Full month' for row in rows[1:-1]))
        self.assertEqual([row[0] for row in rows[1:]], sorted(row[0] for row in rows[1:]))

    def test_submission_yearly_export_matches_all_six_years(self):
        with mock.patch('console.views.timezone.localdate', return_value=date(2026, 1, 15)):
            rows = self.assert_export_matches_table(
                'submission_stats', 'submission-yearly-stats-2026-01-15.csv',
                table_id='submission-yearly-activity-table', table='yearly',
            )
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[-1][-1], 'Partial year')
        self.assertTrue(all(row[-1] == 'Full year' for row in rows[1:-1]))

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

    def test_submission_activity_marks_partial_periods_and_explains_events(self):
        with mock.patch('console.views.timezone.localdate', return_value=date(2026, 1, 15)):
            page = self.client.get(reverse('submission_stats'))
        self.assertContains(page, 'January*')
        self.assertContains(page, '2026*')
        self.assertContains(page, 'Project activity by month')
        self.assertContains(page, 'edit-log events by submission date')
        self.assertContains(page, 'not conversion rates')

    @override_settings(TIME_ZONE='America/New_York')
    def test_submission_creation_year_uses_site_timezone(self):
        from django.utils import timezone
        from project.models import ActiveProject
        project = ActiveProject.objects.first()
        params = {'export': 'csv', 'table': 'yearly'}
        with timezone.override('America/New_York'), mock.patch(
                'console.views.timezone.localdate', return_value=date(2026, 1, 15)):
            ActiveProject.objects.filter(pk=project.pk).update(
                creation_datetime=datetime(2026, 1, 1, 1, tzinfo=dt_timezone.utc))
            early = self.client.get(reverse('submission_stats'), params)
            ActiveProject.objects.filter(pk=project.pk).update(
                creation_datetime=datetime(2026, 1, 1, 12, tzinfo=dt_timezone.utc))
            later = self.client.get(reverse('submission_stats'), params)

        def counts(response):
            return {row['Year']: int(row['Created'])
                    for row in csv.DictReader(StringIO(response.content.decode()))}
        self.assertEqual(counts(later)['2026'], counts(early)['2026'] + 1)
        self.assertEqual(counts(later)['2025'], counts(early)['2025'] - 1)

    def test_submission_charts_match_csv_values_and_tables_start_collapsed(self):
        import json
        with mock.patch('console.views.timezone.localdate', return_value=date(2026, 1, 15)):
            page = self.client.get(reverse('submission_stats'))
            for period, parameter in (('monthly', 'monthly'), ('yearly', 'yearly')):
                response = self.client.get(reverse('submission_stats'), {'export': 'csv', 'table': parameter})
                rows = list(csv.DictReader(StringIO(response.content.decode())))
                charts = page.context[f'{period}_charts']
                for panel, names in (('created', ['Created']),
                                     ('activity', ['Submitted', 'Resubmitted', 'Published', 'Rejected'])):
                    chart = charts[panel]
                    self.assertEqual(chart['period_unit'], 'month' if period == 'monthly' else 'year')
                    self.assertEqual(chart['partial_through'], '2026-01-15')
                    if panel == 'created':
                        self.assertFalse(chart['legend'])
                    self.assertEqual(chart['labels'], [row['Period (YYYY-MM)' if period == 'monthly' else 'Year']
                                                       for row in rows])
                    self.assertEqual(chart['partial'], [row['Period coverage'].startswith('Partial') for row in rows])
                    self.assertEqual([series['name'] for series in chart['series']], names)
                    for series in chart['series']:
                        self.assertEqual(series['values'], [int(row[series['name']]) for row in rows])
                    identifier = f'submission-{period}-{panel}'
                    self.assertContains(page, f'id="{identifier}" type="application/json"')
                    # json_script serializes the same chart payload used by the SVG renderer.
                    self.assertContains(page, json.dumps(chart))
        self.assertContains(page, '<details><summary>Show monthly table</summary>')
        self.assertContains(page, '<details><summary>Show annual table</summary>')
        self.assertNotContains(page, '<details open')

    @override_settings(TIME_ZONE='America/New_York')
    def test_editorial_publication_year_uses_site_timezone(self):
        from django.utils import timezone
        from project.models import PublishedProject
        project = PublishedProject.objects.filter(is_legacy=False).first()
        with timezone.override('America/New_York'):
            PublishedProject.objects.filter(pk=project.pk).update(
                publish_datetime=datetime(2026, 1, 1, 1, tzinfo=dt_timezone.utc))
            early = self.client.get(reverse('editorial_stats'), {'export': 'csv'})
            PublishedProject.objects.filter(pk=project.pk).update(
                publish_datetime=datetime(2026, 1, 1, 12, tzinfo=dt_timezone.utc))
            later = self.client.get(reverse('editorial_stats'), {'export': 'csv'})

        def counts(response):
            return {row['Year']: int(row['Total publications'])
                    for row in csv.DictReader(StringIO(response.content.decode()))}

        self.assertEqual(counts(later).get('2026', 0), counts(early).get('2026', 0) + 1)
        self.assertEqual(counts(later).get('2025', 0), counts(early).get('2025', 0) - 1)

    @override_settings(TIME_ZONE='America/New_York')
    def test_editorial_first_decision_uses_local_month_and_year(self):
        from django.utils import timezone
        from console.reporting import period
        from project.models import ActiveProject, PublishedProject, EditLog
        EditLog.objects.all().delete()
        ActiveProject.objects.update(submission_datetime=None)
        PublishedProject.objects.update(submission_datetime=None)
        projects = list(ActiveProject.objects.all()[:2])
        self.assertEqual(len(projects), 2)
        with timezone.override('America/New_York'):
            for project, hour, days in zip(projects, (4, 5), (1, 2)):
                # 04:30 UTC is Dec 31 23:30 local; 05:30 UTC is Jan 1 00:30 local.
                decided = datetime(2026, 1, 1, hour, 30, tzinfo=dt_timezone.utc)
                submitted = decided - timezone.timedelta(days=days)
                ActiveProject.objects.filter(pk=project.pk).update(submission_datetime=submitted)
                EditLog.objects.create(project=project, submission_datetime=submitted,
                                       decision=1, decision_datetime=decided)
                self.assertEqual(period(decided), '2025-12' if hour == 4 else '2026-01')
            response = self.client.get(reverse('editorial_stats'), {'export': 'csv'})
        rows = {row['Year']: row for row in csv.DictReader(StringIO(response.content.decode()))}
        column = 'Submission to first decision (median days)'
        self.assertEqual(float(rows['2025'][column]), 1)
        self.assertEqual(float(rows['2026'][column]), 2)
