import csv
from datetime import date, datetime, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from console.metrics_test_utils import MetricsTestCase
from console.usage import usage_metrics
from console.usage_trends import usage_trends
from project.models import AccessLog, PublishedProject


class TestUsageTrends(MetricsTestCase):
    def setUp(self):
        super().setUp()
        # Keep aggregation tests independent of the separately tested availability bounds.
        bounds = patch('console.views.usage_record_dates', return_value={'first': None, 'last': None})
        bounds.start()
        self.addCleanup(bounds.stop)

    def test_monthly_counts_deduplicate_people_and_fill_gaps(self):
        AccessLog.objects.all().delete()
        jan = timezone.make_aware(datetime(2020, 1, 10))
        march = timezone.make_aware(datetime(2020, 3, 10))
        self.create_log(self.dataset, self.viewer, jan)
        self.create_log(self.version, self.viewer, jan)
        self.create_log(self.dataset, self.viewer, march)
        self.create_log(self.dataset, self.other, march)
        self.create_log(self.active, self.coauthor, jan)
        self.create_log(PublishedProject.objects.filter(resource_type_id=1).first(), self.coauthor, jan)
        report = usage_trends(date(2020, 1, 1), date(2020, 3, 31))
        self.assertEqual(report['rows'], [
            ['2020-01', 1, 2, 'Full month'], ['2020-02', 0, 0, 'Full month'],
            ['2020-03', 2, 2, 'Full month'],
        ])
        self.assertEqual(report['charts'][0]['chart']['series'][0]['values'], [1, 0, 2])
        self.assertEqual(report['charts'][1]['chart']['series'][0]['values'], [2, 0, 2])

    def test_spanning_sessions_are_not_imputed_to_later_months(self):
        AccessLog.objects.all().delete()
        self.create_log(self.dataset, self.viewer, timezone.make_aware(datetime(2019, 12, 31)),
                        timezone.make_aware(datetime(2020, 3, 1)))
        report = usage_trends(date(2020, 1, 1), date(2020, 3, 31))
        self.assertTrue(all(row[1:3] == [0, 0] for row in report['rows']))
        summary = usage_metrics(date(2020, 1, 1), date(2020, 3, 31))
        overview = {row['label']: row['count'] for row in summary[0]['rows']}
        self.assertEqual(overview['Unique registered dataset viewers'], 1)

    @override_settings(TIME_ZONE='America/New_York')
    def test_local_month_and_inclusive_date_boundaries(self):
        AccessLog.objects.all().delete()
        with timezone.override('America/New_York'):
            self.create_log(self.dataset, self.viewer, datetime(2020, 1, 1, 4, 30, tzinfo=dt_timezone.utc))
            self.create_log(self.dataset, self.other, datetime(2020, 1, 1, 5, 30, tzinfo=dt_timezone.utc))
            self.create_log(self.dataset, self.coauthor, datetime(2020, 2, 1, 5, tzinfo=dt_timezone.utc))
            report = usage_trends(date(2020, 1, 1), date(2020, 1, 31))
        self.assertEqual(report['rows'], [['2020-01', 1, 1, 'Full month']])

    def test_partial_months_and_empty_selection(self):
        report = usage_trends(date(2010, 1, 10), date(2010, 3, 20))
        self.assertEqual([row[3] for row in report['rows']], ['Partial month', 'Full month', 'Partial month'])
        self.assertEqual(report['charts'][0]['chart']['partial'], [True, False, True])
        with patch('console.usage_trends.timezone.localdate', return_value=date(2020, 6, 15)):
            current = usage_trends(date(2020, 6, 1), date(2020, 6, 30))
        self.assertEqual(current['rows'][0][3], 'Partial month')

    def test_page_chart_table_and_csv_share_values_and_permissions(self):
        url = reverse('usage_stats')
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        self.assertEqual(self.client.get(url, {**params, 'export': 'monthly'}).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url, {**params, 'export': 'monthly'}).status_code, 403)
        self.client.force_login(self.admin)
        page = self.client.get(url, params)
        self.assertEqual(page.status_code, 200)
        report = page.context['usage_trend']
        exported = self.client.get(url, {**params, 'export': 'monthly'})
        rows = list(csv.reader(StringIO(exported.content.decode())))
        self.assertEqual(rows, [report['headers'], *[[str(cell) for cell in row] for row in report['rows']]])
        self.assertContains(page, '<details>\n      <summary>Show monthly table</summary>')
        self.assertNotContains(page, '<details open')
        self.assertContains(page, 'data-metrics-chart="usage-monthly-viewers"')
        self.assertContains(page, 'data-metrics-chart="usage-monthly-sessions"')
        invalid = self.client.get(url, {'start_date': 'bad', 'export': 'monthly'})
        self.assertEqual(invalid.status_code, 400)
        self.assertNotIn('Content-Disposition', invalid)

    def test_country_trend_deduplicates_viewers_and_exports_coverage(self):
        from console.usage_trends import usage_country_trends
        from user.models import CredentialApplication
        AccessLog.objects.all().delete()
        jan = timezone.make_aware(datetime(2020, 1, 10))
        self.create_log(self.dataset, self.viewer, jan)
        self.create_log(self.version, self.viewer, jan)
        self.create_log(self.dataset, self.other, jan)
        self.create_log(self.dataset, self.coauthor, jan)
        CredentialApplication.objects.create(user=self.coauthor, slug='country-missing',
                                             status=CredentialApplication.Status.ACCEPTED, country='ZZ',
                                             researcher_category=0)
        monthly = usage_trends(date(2020, 1, 1), date(2020, 2, 29))
        report = usage_country_trends(date(2020, 1, 1), date(2020, 2, 29), monthly)
        self.assertEqual(report['chart']['series'][0]['values'], [1, 0])
        self.assertEqual(report['chart']['series'][0]['name'], 'United States')
        rows = [dict(zip(report['export']['headers'], row)) for row in report['export']['rows']]
        jan_rows = [row for row in rows if row['Period (YYYY-MM)'] == '2020-01']
        self.assertEqual(sum(row['Unique registered viewers'] for row in jan_rows), 3)
        self.assertTrue(all(row['All registered viewers'] == 3 for row in jan_rows))
        self.assertTrue(all(row['Coverage (%)'] == 33.33 for row in jan_rows))
        self.assertEqual({row['Country'] for row in jan_rows if row['Row type'] == 'unavailable'},
                         {'No approved credential application', 'Information missing or unrecognized'})
        known = next(row for row in jan_rows if row['Row type'] == 'category')
        self.assertEqual(known['With information (%)'], 100.0)
        self.assertEqual(report['rows'][1][-2], None)
        self.assertEqual(report['approved_rows'][0][-4:], [2, 1, 50.0, 'Full month'])
        self.assertEqual(report['without_approval']['chart']['series'][0]['values'], [1, 0])

    def test_country_trend_uses_current_approved_country_not_historical_country(self):
        from console.usage_trends import usage_country_trends
        from user.models import CredentialApplication
        monthly = usage_trends(date(2020, 1, 1), date(2020, 12, 31))
        CredentialApplication.objects.filter(user=self.viewer, status=CredentialApplication.Status.ACCEPTED).update(
            country='BR')
        report = usage_country_trends(date(2020, 1, 1), date(2020, 12, 31), monthly)
        self.assertEqual(report['chart']['series'][0]['name'], 'Brazil')
        self.assertEqual(report['chart']['series'][0]['values'][5], 1)

    def test_country_monthly_export_matches_chart_and_requires_permission(self):
        url = reverse('usage_stats')
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31', 'export': 'country-monthly'}
        self.assertEqual(self.client.get(url, params).status_code, 403)
        self.client.force_login(self.admin)
        page = self.client.get(url, {k: v for k, v in params.items() if k != 'export'})
        section = next(s for s in page.context['sections'] if s['title'] == 'Dataset viewers by country')
        report = section['country_trend']
        response = self.client.get(url, params)
        exported = list(csv.reader(StringIO(response.content.decode())))
        self.assertEqual(exported, [report['export']['headers'], *[
            ['' if cell is None else str(cell) for cell in row] for row in report['export']['rows']]])
        self.assertContains(page, 'data-metrics-chart="usage-country-monthly"')
        self.assertContains(page, 'not historical location')
        invalid = self.client.get(url, {**params, 'start_date': 'invalid'})
        self.assertEqual(invalid.status_code, 400)

    def test_country_trend_keeps_top_five_fixed_and_other_counts_complete(self):
        from console.usage_trends import usage_country_trends
        from user.models import CredentialApplication, User
        AccessLog.objects.all().delete()
        for code in ('BR', 'CN', 'DE', 'GB', 'IN', 'KR'):
            user = User.objects.create_user(f'trend-{code}@example.com', 'password', f'trend-{code}')
            CredentialApplication.objects.create(user=user, slug=f'trend-{code}', country=code,
                                                 status=CredentialApplication.Status.ACCEPTED, researcher_category=0)
            self.create_log(self.dataset, user, timezone.make_aware(datetime(2020, 1, 10)))
            if code == 'KR':
                # Many sessions from one person must not push their country into the top five.
                for _ in range(3):
                    self.create_log(self.dataset, user, timezone.make_aware(datetime(2020, 2, 10)))
        monthly = usage_trends(date(2020, 1, 1), date(2020, 2, 29))
        report = usage_country_trends(date(2020, 1, 1), date(2020, 2, 29), monthly)
        self.assertEqual(len(report['chart']['series']), 5)
        self.assertTrue(all(series['values'] == [1, 0] for series in report['chart']['series']))
        self.assertEqual(report['rows'][0][6:10], [1, 0, 6, 6])
        self.assertEqual(report['rows'][1][6:10], [1, 0, 1, 1])
        exported = [dict(zip(report['export']['headers'], row)) for row in report['export']['rows']]
        self.assertEqual(sum(row['Unique registered viewers'] for row in exported
                             if row['Period (YYYY-MM)'] == '2020-02'), 1)

    def test_country_trend_handles_empty_and_unknown_populations(self):
        from console.usage_trends import usage_country_trends
        AccessLog.objects.all().delete()
        monthly = usage_trends(date(2020, 1, 1), date(2020, 1, 31))
        empty = usage_country_trends(date(2020, 1, 1), date(2020, 1, 31), monthly)
        self.assertFalse(empty['has_countries'])
        self.assertEqual(empty['export']['rows'][0][3], 'empty')
        self.create_log(self.dataset, self.other, timezone.make_aware(datetime(2020, 1, 10)))
        unknown = usage_country_trends(date(2020, 1, 1), date(2020, 1, 31), monthly)
        self.assertFalse(unknown['has_countries'])
        self.assertEqual(unknown['export']['rows'][0][3:5], ['unavailable', 1])

    def test_approval_groups_are_separate_and_nonapproved_export_matches(self):
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        url = reverse('usage_stats')
        page = self.client.get(url, params)
        country = next(s for s in page.context['sections'] if s['title'] == 'Dataset viewers by country')
        self.assertEqual(country['approved_group_total'], 1)
        self.assertEqual(country['without_approval']['total'], 1)
        self.assertEqual(country['approved_group_coverage'], 100.0)
        self.assertContains(page, 'Registered viewers with an approved credential application')
        self.assertContains(page, 'id="viewers-without-approved-application"')
        self.assertContains(page, 'data-metrics-chart="usage-without-approval-monthly"')
        exported = self.client.get(url, {**params, 'export': 'unapproved-monthly'})
        rows = list(csv.reader(StringIO(exported.content.decode())))
        report = country['without_approval']
        self.assertEqual(rows, [report['headers'], *[[str(cell) for cell in row] for row in report['rows']]])
        self.client.logout()
        self.assertEqual(self.client.get(url, {**params, 'export': 'unapproved-monthly'}).status_code, 403)

    def test_category_trend_deduplicates_and_accepts_category_zero(self):
        from console.usage_trends import usage_category_trend
        from user.models import CredentialApplication
        CredentialApplication.objects.create(user=self.other, slug='category-zero', country='BR',
                                             status=CredentialApplication.Status.ACCEPTED, researcher_category=0)
        monthly = usage_trends(date(2020, 1, 1), date(2020, 12, 31))
        report = usage_category_trend(date(2020, 1, 1), date(2020, 12, 31), monthly)
        label = dict(CredentialApplication.RESEARCHER_CATEGORIES)[0]
        series = next(s for s in report['chart']['series'] if s['name'] == label)
        self.assertEqual(series['values'], [0] * 5 + [1] + [0] * 6)
        self.assertEqual(report['rows'][5][-4:-1], [2, 2, 100.0])

    def test_category_trend_separates_missing_fields_from_no_approved_application(self):
        from console.usage_trends import usage_category_trend
        from user.models import CredentialApplication
        CredentialApplication.objects.filter(user=self.viewer, status=CredentialApplication.Status.ACCEPTED).update(
            researcher_category=99)
        monthly = usage_trends(date(2020, 1, 1), date(2020, 12, 31))
        report = usage_category_trend(date(2020, 1, 1), date(2020, 12, 31), monthly)
        self.assertEqual(report['rows'][5][-6:-1], [1, 1, 0, 2, 0.0])
        self.assertTrue(all(series['values'][5] == 0 for series in report['chart']['series']))
        self.assertIsNone(report['rows'][0][-2])

    def test_country_and_category_trends_share_one_demographic_query_pair(self):
        from console.usage_trends import usage_monthly_demographics, usage_category_trend, usage_country_trends
        start, end = date(2020, 1, 1), date(2020, 12, 31)
        monthly = usage_trends(start, end)
        with self.assertNumQueries(2):
            data = usage_monthly_demographics(start, end, monthly)
            country = usage_country_trends(start, end, monthly, data)
            category = usage_category_trend(start, end, monthly, data)
        self.assertEqual(country['rows'][5][-4], category['rows'][5][-3])

    def test_all_category_series_and_csv_share_the_same_values(self):
        from user.models import CredentialApplication
        self.client.force_login(self.admin)
        url = reverse('usage_stats')
        dates = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        page = self.client.get(url, dates)
        section = next(s for s in page.context['sections']
                       if s['title'] == 'Dataset viewers by researcher category')
        report = section['category_trend']
        series = report['chart']['series']
        self.assertEqual({s['name'] for s in series}, set(dict(CredentialApplication.RESEARCHER_CATEGORIES).values()))
        self.assertEqual(len({s['color'] for s in series}), len(series))
        self.assertEqual(len({s['marker'] for s in series}), len(series))
        for item in series:
            column = report['headers'].index(item['name'])
            self.assertEqual(item['values'], [row[column] for row in report['rows']])
        self.assertNotContains(page, 'data-category-filter')
        self.assertNotContains(page, 'name="researcher_category"')
        self.assertContains(page, 'data-metrics-chart="usage-category-monthly"')
        exported = self.client.get(url, {**dates, 'export': 'category-monthly'})
        rows = list(csv.reader(StringIO(exported.content.decode())))
        self.assertEqual(rows, [report['headers'], *[
            ['' if cell is None else str(cell) for cell in row] for row in report['rows']]])
        self.client.logout()
        self.assertEqual(self.client.get(url, {**dates, 'export': 'category-monthly'}).status_code, 403)

    def test_category_legend_orders_by_period_unique_viewers_not_monthly_sum(self):
        from console.usage_trends import usage_category_trend
        from user.models import CredentialApplication
        AccessLog.objects.all().delete()
        CredentialApplication.objects.filter(user=self.viewer, status=CredentialApplication.Status.ACCEPTED).update(
            researcher_category=0)
        for index, user in enumerate((self.other, self.coauthor)):
            CredentialApplication.objects.create(user=user, slug=f'legend-category-{index}', country='US',
                                                 status=CredentialApplication.Status.ACCEPTED, researcher_category=1)
            self.create_log(self.dataset, user, timezone.make_aware(datetime(2020, 1, 10)))
        for month in (1, 2, 3):
            self.create_log(self.dataset, self.viewer, timezone.make_aware(datetime(2020, month, 10)))
        monthly = usage_trends(date(2020, 1, 1), date(2020, 3, 31))
        report = usage_category_trend(date(2020, 1, 1), date(2020, 3, 31), monthly)
        self.assertTrue(report['chart']['interactive_legend'])
        series = report['chart']['series']
        self.assertEqual([s['period_count'] for s in series[:2]], [2, 1])
        self.assertEqual(series[0]['values'], [2, 0, 0])
        self.assertEqual(series[1]['values'], [1, 1, 1])
        self.assertEqual(series[0]['name'], dict(CredentialApplication.RESEARCHER_CATEGORIES)[1])

    def test_dataset_trends_combine_versions_without_double_counting_people(self):
        from console.usage_trends import usage_dataset_trends
        sections = {s['title']: s for s in usage_metrics(date(2020, 1, 1), date(2020, 12, 31))}
        monthly = usage_trends(date(2020, 1, 1), date(2020, 12, 31))
        reports = usage_dataset_trends(date(2020, 1, 1), date(2020, 12, 31), monthly,
                                       sections['Most accessed datasets']['rows'],
                                       sections['Registered viewers by dataset version']['rows'])
        self.assertEqual(reports['datasets']['chart']['series'][0]['values'][5], 2)
        by_version = {s['name']: s['values'][5] for s in reports['versions']['chart']['series']}
        self.assertEqual(by_version[f'{self.dataset.slug} / {self.dataset.version}'], 1)
        self.assertEqual(by_version[f'{self.version.slug} / {self.version.version}'], 2)
        self.assertEqual(reports['datasets']['rows'][0][1], 0)
        for report in reports.values():
            self.assertTrue(report['chart']['interactive_legend'])
            for index, series in enumerate(report['chart']['series'], 1):
                self.assertEqual(series['values'], [row[index] for row in report['rows']])

    def test_dataset_rankings_are_top_ten_and_account_age_is_last(self):
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        page = self.client.get(reverse('usage_stats'), params)
        self.assertEqual(page.context['sections'][-1]['title'], 'Dataset viewers by account age')
        age = page.context['sections'][-1]
        self.assertEqual(age['pie_chart']['type'], 'pie')
        self.assertEqual([s['values'][0] for s in age['pie_chart']['series']], [r['count'] for r in age['rows']])
        self.assertContains(page, 'data-metrics-chart="usage-account-age"')
        self.assertContains(page, 'data-metrics-chart="usage-datasets-monthly"')
        self.assertContains(page, 'data-metrics-chart="usage-versions-monthly"')
        for section in page.context['sections']:
            if section['title'] in ('Most accessed datasets', 'Registered viewers by dataset version'):
                self.assertLessEqual(len(section['rows']), 10)
        for key in ('datasets', 'versions'):
            exported = self.client.get(reverse('usage_stats'), {**params, 'export': key + '-monthly'})
            identifier = 'usage-' + key + '-monthly'
            section = next(s for s in page.context['sections']
                           if s.get('dataset_trend', {}).get('id') == identifier)
            report = section['dataset_trend']
            rows = list(csv.reader(StringIO(exported.content.decode())))
            self.assertEqual(rows, [report['headers'], *[[str(cell) for cell in row] for row in report['rows']]])
        self.client.logout()
        response = self.client.get(reverse('usage_stats'), {**params, 'export': 'datasets-monthly'})
        self.assertEqual(response.status_code, 403)

    def test_account_age_csv_contains_only_the_pie_data(self):
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        page = self.client.get(reverse('usage_stats'), params)
        age = next(s for s in page.context['sections'] if s['title'] == 'Dataset viewers by account age')
        exported = self.client.get(reverse('usage_stats'), {**params, 'export': 'account-age'})
        rows = list(csv.DictReader(StringIO(exported.content.decode())))
        self.assertEqual({row['Section'] for row in rows}, {'Dataset viewers by account age'})
        self.assertEqual([(r['Metric'], int(r['Count'])) for r in rows],
                         [(r['label'], r['count']) for r in age['rows']])
        self.client.logout()
        response = self.client.get(reverse('usage_stats'), {**params, 'export': 'account-age'})
        self.assertEqual(response.status_code, 403)
