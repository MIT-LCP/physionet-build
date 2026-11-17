import csv
from datetime import date, datetime, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from console.access_trends import ACCESS_DATES_CACHE_KEY, access_record_dates, approved_user_trends
from console.metrics_test_utils import MetricsTestCase
from console.usage import UsageDateForm
from project.models import DataAccessRequest, PublishedProject
from user.models import CredentialApplication


class TestAccessTrends(MetricsTestCase):
    def setUp(self):
        super().setUp()
        cache.delete(ACCESS_DATES_CACHE_KEY)
        self.addCleanup(cache.delete, ACCESS_DATES_CACHE_KEY)

    def reports(self):
        return approved_user_trends(date(2020, 1, 1), date(2020, 12, 31))

    def test_monthly_people_are_unique_across_versions_and_can_reappear_in_later_months(self):
        july = timezone.make_aware(datetime(2020, 7, 1))
        self.create_request(self.viewer)
        self.create_request(self.viewer, project=self.version)
        self.create_request(self.viewer, project=self.version, status=DataAccessRequest.REVOKED_VALUE,
                            decided=july)
        self.create_request(self.other)
        self.create_request(self.coauthor, status=DataAccessRequest.REJECT_REQUEST_VALUE)
        self.create_request(self.coauthor, status=DataAccessRequest.PENDING_VALUE)
        self.create_request(self.coauthor, project=PublishedProject.objects.filter(resource_type_id=1).first())
        reports = self.reports()
        for report in reports.values():
            june, july_row = (dict(zip(report['headers'], report['rows'][i])) for i in (5, 6))
            self.assertEqual(june['Unique approved users'], 2)
            self.assertEqual(june['No approved credential application'], 1)
            self.assertEqual(june['Users with information'], 1)
            self.assertEqual(june['Coverage (%)'], 50.0)
            self.assertEqual(july_row['Unique approved users'], 1)
            self.assertEqual(july_row['Coverage (%)'], 100.0)
            self.assertEqual(report['chart']['series'][0]['values'][5:7], [1, 1])
            self.assertEqual(report['chart']['series'][0]['period_count'], 1)
            self.assertTrue(report['chart']['interactive_legend'])
            self.assertEqual(len(report['rows']), 12)
            self.assertEqual(report['rows'][0][-2:], [None, 'Full month'])

    @override_settings(TIME_ZONE='America/New_York')
    def test_month_is_decision_month_in_site_timezone_with_inclusive_boundaries(self):
        with timezone.override('America/New_York'):
            self.create_request(self.viewer, requested=timezone.make_aware(datetime(2019, 1, 1)),
                                decided=datetime(2020, 1, 1, 4, 30, tzinfo=dt_timezone.utc))
            self.create_request(self.viewer, decided=datetime(2020, 1, 1, 5, 30, tzinfo=dt_timezone.utc))
            self.create_request(self.viewer, decided=datetime(2020, 2, 1, 5, 0, tzinfo=dt_timezone.utc))
            report = approved_user_trends(date(2020, 1, 1), date(2020, 1, 31))['country']
        row = dict(zip(report['headers'], report['rows'][0]))
        self.assertEqual(row['Unique approved users'], 1)
        self.assertEqual(report['chart']['series'][0]['values'], [1])

    def test_current_credential_information_and_missing_reasons_are_separate(self):
        self.create_request(self.viewer)
        self.create_request(self.other)
        CredentialApplication.objects.filter(user=self.viewer, status=CredentialApplication.Status.ACCEPTED).update(
            country='ZZ', researcher_category=99)
        for report in self.reports().values():
            self.assertEqual(report['chart']['series'], [])
            june = dict(zip(report['headers'], report['rows'][5]))
            self.assertEqual(june['No approved credential application'], 1)
            self.assertEqual(june['Information missing or unrecognized'], 1)
            self.assertEqual(june['Users with information'], 0)
            self.assertEqual(june['Coverage (%)'], 0.0)

    def test_empty_reports_have_zero_counts_and_no_percentage(self):
        for report in self.reports().values():
            self.assertEqual(report['chart']['series'], [])
            self.assertTrue(all(row[1:5] == [0, 0, 0, 0] for row in report['rows']))
            self.assertTrue(all(row[-2] is None for row in report['rows']))

    def test_country_ranking_uses_period_people_not_sum_of_monthly_people(self):
        self.create_request(self.viewer)
        self.create_request(self.viewer, decided=timezone.make_aware(datetime(2020, 7, 1)))
        self.create_request(self.viewer, decided=timezone.make_aware(datetime(2020, 8, 1)))
        for user in (self.other, self.coauthor):
            self.create_request(user)
            self.credential_for(user, 'BR', 2)
        reports = self.reports()
        countries = reports['country']['chart']['series']
        self.assertEqual([series['name'] for series in countries], ['Brazil', 'United States of America'])
        self.assertEqual([series['period_count'] for series in countries], [2, 1])
        categories = reports['category']['chart']['series']
        self.assertEqual([series['period_count'] for series in categories], [2, 1])

    def credential_for(self, user, country, category):
        CredentialApplication.objects.create(
            user=user, slug='access-trend-' + str(user.pk), country=country, researcher_category=category,
            status=CredentialApplication.Status.ACCEPTED,
        )

    def test_page_order_cards_collapsed_tables_and_exports_match_chart_values(self):
        self.create_request(self.viewer, requested=timezone.make_aware(datetime(2019, 1, 1)))
        self.client.force_login(self.admin)
        url = reverse('access_request_stats')
        self.create_request(self.other, status=DataAccessRequest.PENDING_VALUE)
        params = {'start_date': '2020-06-15', 'end_date': '2020-07-15'}
        page = self.client.get(url, params)
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        self.assertLess(html.index('id="access-period"'), html.index('aria-label="Access requests overview"'))
        self.assertLess(html.index('aria-label="Access requests overview"'), html.index('data-metrics-chart='))
        self.assertLess(html.index('data-metrics-chart='), html.index('id="current-access-queue"'))
        self.assertNotIn('<details open', html)
        self.assertContains(page, 'Download data (CSV)', count=5)
        self.assertContains(page, 'data-chart-downloads-for=', count=5)
        self.assertContains(page, 'Show monthly table and coverage', count=3)
        self.assertNotContains(page, '>Dataset access requests by month<')
        self.assertContains(page, 'metrics-chart-export.js')
        self.assertTrue(page.context['sections'][0]['display_cards'])
        self.assertEqual(page.context['report']['chart']['partial'], [True, True])
        for field in ('country', 'category'):
            section = next(s for s in page.context['sections']
                           if s.get('access_trend', {}).get('id') == 'access-' + field + '-monthly')
            report = section['access_trend']
            response = self.client.get(url, {**params, 'export': field + '-monthly'})
            rows = list(csv.DictReader(StringIO(response.content.decode())))
            self.assertEqual(len(rows), len(report['rows']))
            for i, row in enumerate(rows):
                for series in report['chart']['series']:
                    self.assertEqual(int(row[series['name']]), series['values'][i])
                self.assertEqual(row['Period coverage'], report['rows'][i][-1])
        summary = self.client.get(url, {**params, 'export': 'csv'})
        self.assertIn('Dataset access requests by month', summary.content.decode())

    def test_demographic_csvs_require_stats_permission(self):
        url = reverse('access_request_stats')
        for export in ('country-monthly', 'category-monthly'):
            self.assertEqual(self.client.get(url, {'export': export}).status_code, 403)
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(url, {'export': export}).status_code, 403)
            self.client.logout()

    def test_bounds_ignore_other_resources_use_request_and_decision_dates_and_cache(self):
        requested = timezone.make_aware(datetime(2019, 12, 1))
        self.create_request(self.viewer, requested=requested)
        self.create_request(self.other, requested=timezone.make_aware(datetime(2018, 1, 1)),
                            project=PublishedProject.objects.filter(resource_type_id=1).first())
        self.assertEqual(access_record_dates(), {'first': date(2019, 12, 1), 'last': date(2020, 6, 15)})
        with self.assertNumQueries(0):
            self.assertEqual(access_record_dates()['first'], date(2019, 12, 1))
        cache.delete(ACCESS_DATES_CACHE_KEY)
        DataAccessRequest.objects.all().delete()
        self.assertEqual(access_record_dates(), {'first': None, 'last': None})

    def test_filter_enforces_first_record_for_page_and_csv_but_not_snapshot_exports(self):
        self.create_request(self.viewer, status=DataAccessRequest.PENDING_VALUE)
        self.client.force_login(self.admin)
        url = reverse('access_request_stats')
        params = {'start_date': '2010-01-01', 'end_date': '2010-12-31'}
        for export in ('', 'csv', 'monthly', 'country-monthly', 'category-monthly'):
            response = self.client.get(url, {**params, 'export': export})
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, 'Start date cannot be before', status_code=400)
        for export in ('pending', 'pending-datasets', 'pending-versions', 'pending-monthly'):
            self.assertEqual(self.client.get(url, {**params, 'export': export}).status_code, 200)
        default = self.client.get(url)
        self.assertEqual(default.status_code, 200)
        self.assertContains(default, 'min="2020-06-15"')
        form = UsageDateForm({'start_date': '2020-06-15', 'end_date': timezone.localdate()},
                             first_record_date=date(2020, 6, 15))
        self.assertTrue(form.is_valid())

    def test_default_start_moves_forward_when_history_starts_this_year(self):
        self.client.force_login(self.admin)
        today = timezone.localdate()
        first = today.replace(month=1, day=2)
        with patch('console.views.access_record_dates', return_value={'first': first, 'last': first}):
            response = self.client.get(reverse('access_request_stats'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].cleaned_data['start_date'], first)

    def test_current_pending_monthly_distribution_matches_entire_queue_not_selected_dates(self):
        from console.access_trends import pending_request_trend
        from console.reporting import pending_access_requests
        now = timezone.make_aware(datetime(2020, 8, 10))
        june = timezone.make_aware(datetime(2020, 6, 15))
        july = timezone.make_aware(datetime(2020, 7, 1))
        self.create_request(self.viewer, status=DataAccessRequest.PENDING_VALUE, requested=june)
        self.create_request(self.viewer, project=self.version, status=DataAccessRequest.PENDING_VALUE, requested=june)
        self.create_request(self.other, status=DataAccessRequest.PENDING_VALUE, requested=july)
        self.create_request(self.coauthor, status=DataAccessRequest.REJECT_REQUEST_VALUE, requested=june)
        queue = list(pending_access_requests(now))
        report = pending_request_trend(queue, now)
        self.assertEqual(report['chart']['labels'], ['2020-06', '2020-07', '2020-08'])
        self.assertEqual(report['chart']['series'][0]['values'], [2, 1, 0])
        self.assertEqual(sum(row[1] for row in report['rows']), len(queue))
        self.assertTrue(all(row[2] == now.isoformat() for row in report['rows']))
        self.assertIn('not the queue size at past dates', report['description'])
        self.client.force_login(self.admin)
        with patch('console.views.timezone.now', return_value=now):
            response = self.client.get(reverse('access_request_stats'), {
                'start_date': '2010-01-01', 'end_date': '2010-02-01', 'export': 'pending-monthly'})
        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual([int(row['Currently pending requests']) for row in rows], [2, 1, 0])
        self.assertTrue(all(row['Snapshot'] == now.isoformat() for row in rows))

    def test_empty_pending_queue_has_a_zero_month_and_snapshot(self):
        from console.access_trends import pending_request_trend
        report = pending_request_trend([], self.when)
        self.assertEqual(report['chart']['series'][0]['values'], [0])
        self.assertEqual(report['rows'][0][2], self.when.isoformat())

    def test_account_age_pie_precedes_final_pending_summary_and_has_its_own_csv(self):
        from user.models import User
        User.objects.filter(pk=self.viewer.pk).update(join_date=date(2020, 6, 1))
        User.objects.filter(pk=self.other.pk).update(join_date=date(2019, 12, 31))
        self.create_request(self.viewer)
        self.create_request(self.viewer, project=self.version)
        self.create_request(self.other)
        self.client.force_login(self.admin)
        url = reverse('access_request_stats')
        params = {'start_date': '2020-06-01', 'end_date': '2020-12-31'}
        with patch('console.views.access_record_dates', return_value={'first': None, 'last': None}):
            page = self.client.get(url, params)
            response = self.client.get(url, {**params, 'export': 'account-age'})
        age = page.context['access_account_age_sections'][0]
        self.assertEqual([series['values'][0] for series in age['pie_chart']['series']], [1, 1])
        self.assertEqual([series['color'] for series in age['pie_chart']['series']], ['#2563eb', '#ea580c'])
        self.assertEqual([row['count'] for row in age['rows']], [1, 1])
        html = page.content.decode()
        self.assertLess(html.index('id="current-access-queue"'), html.index('data-metrics-chart="access-account-age"'))
        self.assertLess(html.index('data-metrics-chart="access-account-age"'), html.index('id="pending-by-dataset"'))
        self.assertNotContains(page, 'Download version summary CSV')
        self.assertNotContains(page, '<summary>More exports</summary>')
        self.assertContains(page, 'class="btn btn-sm metrics-download">Download datasets (CSV)</a>')
        self.assertContains(page, 'class="btn btn-sm metrics-download">Download versions (CSV)</a>')
        self.assertContains(page, '<summary>Show account age table</summary>')
        self.assertContains(page, '<summary>Show current pending requests table</summary>')
        self.assertNotIn('table-warning', html)
        self.assertNotIn('Download dataset summary CSV', html)
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual([int(row['Count']) for row in rows], [1, 1])
        self.assertTrue(all(row['Section'] == age['title'] for row in rows))
