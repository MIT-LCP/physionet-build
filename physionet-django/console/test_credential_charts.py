import csv
from datetime import date, datetime
from io import StringIO

from django.urls import reverse
from django.utils import timezone

from console.credential_charts import credential_chart_panels
from console.metrics_test_utils import MetricsTestCase
from console.credential_metrics import credential_annual_stats, credential_queue_summary
from user.models import CredentialApplication


class TestCredentialCharts(MetricsTestCase):
    def panels(self):
        return credential_chart_panels(date(2020, 1, 1), date(2020, 12, 31),
                                       credential_annual_stats(), self.when)

    def test_page_has_eleven_charts_in_tab_order_without_tabs_or_individual_lists(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('credentialing_stats'), {'start_date': '2020-01-01',
                                                                    'end_date': '2020-12-31'})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertContains(response, 'data-metrics-chart=', count=11)
        self.assertContains(response, '<summary>Show data table</summary>', count=11)
        self.assertContains(response, 'Download data (CSV)', count=11)
        self.assertNotIn('<details open', html)
        self.assertNotIn('role="tab', html)
        self.assertNotIn('credentialing-tabs.js', html)
        self.assertNotIn('Current pending credential applications', html)
        self.assertNotIn('Most applications per person within the selected period', html)
        self.assertNotIn('repeated_page=', html)
        markers = [html.index(f'id="{identifier}"') for identifier in
                   ('metrics-period', 'credential-trends', 'credential-queue', 'repeated-applications',
                    'credential-annual')]
        self.assertEqual(markers, sorted(markers))
        self.assertContains(response, 'metrics-chart-export.js')
        self.assertNotContains(response, '>Selected period</h2>')
        self.assertContains(response, '>Apply filters</button>')
        self.assertNotContains(response, 'Reporting period')
        self.assertNotContains(response, 'Apply dates')
        self.assertContains(response, 'All application years')

    def test_each_panel_csv_and_chart_come_from_the_same_rows(self):
        self.credential(CredentialApplication.Status.ACCEPTED,
                        decided=self.when + timezone.timedelta(days=2))
        self.client.force_login(self.admin)
        url = reverse('credentialing_stats')
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        page = self.client.get(url, params)
        panels = [*page.context['monthly_panels'], page.context['queue_panel'],
                  *page.context['reapplication_panels'], *page.context['annual_panels']]
        for panel in panels:
            response = self.client.get(url, {**params, 'export': panel['export']})
            self.assertEqual(response.status_code, 200)
            exported = list(csv.reader(StringIO(response.content.decode())))
            self.assertEqual(exported[0], panel['headers'])
            self.assertEqual(exported[1:], [[str(value) if value is not None else '' for value in row]
                                            for row in panel['rows']])
            for series in panel['chart']['series']:
                column = panel['headers'].index(series['name']) if series['name'] in panel['headers'] else None
                if column is not None:
                    expected = [row[column] for row in panel['rows']]
                    if panel.get('snapshot'):
                        expected = expected[:-1]
                    self.assertEqual(series['values'], expected)

    def test_queue_chart_excludes_total_from_stack_and_is_independent_of_reporting_period(self):
        CredentialApplication.objects.all().delete()
        self.credential(CredentialApplication.Status.PENDING, submitted=self.when - timezone.timedelta(days=90))
        first = self.panels()['queue_panel']
        second = credential_chart_panels(date(2010, 1, 1), date(2010, 2, 1),
                                         credential_annual_stats(), self.when)['queue_panel']
        self.assertEqual(first, second)
        self.assertEqual(first['rows'], credential_queue_summary(self.when)['rows'])
        self.assertEqual(len(first['chart']['labels']), 3)
        self.assertNotIn('Total', first['chart']['labels'])
        self.assertEqual(sum(sum(series['values']) for series in first['chart']['series']), 1)
        self.assertEqual(first['start_date'], self.when.date())

    def test_annual_days_and_hours_have_separate_panels_and_keep_missing_values(self):
        CredentialApplication.objects.all().delete()
        self.credential(CredentialApplication.Status.ACCEPTED, decided=self.when + timezone.timedelta(days=3),
                        reference_contact_datetime=self.when + timezone.timedelta(days=1),
                        reference_response_datetime=self.when + timezone.timedelta(days=1, hours=2))
        panels = self.panels()['annual_panels']
        self.assertEqual(panels[2]['chart']['series'][0]['values'], [3.0])
        self.assertEqual(panels[2]['chart']['series'][1]['values'], [1.0])
        self.assertEqual(panels[3]['chart']['series'][0]['values'], [2.0])
        self.assertEqual(panels[2]['chart']['partial'], [True])
        self.assertEqual(panels[3]['chart']['period_unit'], 'year')
        self.assertIsNone(panels[2]['start_date'])
        empty = credential_chart_panels(date(2010, 1, 1), date(2010, 2, 1), {}, self.when)
        self.assertEqual(empty['annual_panels'][0]['chart']['labels'], [])
        self.assertTrue(all(row[5] is None for row in empty['monthly_panels'][0]['rows']))

    def test_new_downloads_require_stats_permission_and_invalid_dates_are_visible(self):
        url = reverse('credentialing_stats')
        for export in ('reapplication-1', 'reapplication-2', 'reapplication-3', 'annual-days', 'annual-response',
                       'annual-approval-share'):
            self.assertEqual(self.client.get(url, {'export': export}).status_code, 403)
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(url, {'export': export}).status_code, 403)
            self.client.logout()
        self.client.force_login(self.admin)
        invalid = self.client.get(url, {'start_date': 'bad'})
        self.assertEqual(invalid.status_code, 400)
        self.assertContains(invalid, 'Enter a valid date', status_code=400)
