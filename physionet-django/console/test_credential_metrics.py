import copy
import csv
from datetime import date, datetime
from io import StringIO
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from console.usage import usage_metrics, usage_sections
from project.models import AccessLog, ActiveProject, Author, DataAccessRequest, PublishedAuthor, PublishedProject
from user.models import CredentialApplication, User


from console.metrics_test_utils import MetricsTestCase


class TestCredentialingMetrics(MetricsTestCase):
    def test_credential_trend_separates_outcomes_and_excludes_negative_durations(self):
        from console.reporting import credential_trend
        CredentialApplication.objects.all().delete()
        accepted = CredentialApplication.Status.ACCEPTED
        self.credential(accepted, decided=self.when + timezone.timedelta(hours=36))
        self.credential(accepted, decided=self.when + timezone.timedelta(days=3))
        self.credential(CredentialApplication.Status.REJECTED, decided=self.when + timezone.timedelta(days=4))
        valid_report = credential_trend(date(2020, 6, 1), date(2020, 7, 31))
        self.assertNotIn('Excluded negative durations', valid_report['description'])
        self.credential(accepted, decided=self.when - timezone.timedelta(days=1))
        report = credential_trend(date(2020, 6, 1), date(2020, 7, 31))
        self.assertEqual(report['rows'], [
            ['2020-06', 2.25, 2, 4.0, 1, 3.0, 3.8, 3, 66.67, 100.0, 'Full month'],
            ['2020-07', None, 0, None, 0, None, None, 0, None, None, 'Full month'],
        ])
        self.assertEqual(report['chart']['series'], [
            {'name': 'Overall median days', 'values': [3.0, None]},
            {'name': 'Overall p90 days', 'values': [3.8, None]},
        ])
        self.assertIn('Excluded negative durations: 1', report['description'])
        self.client.force_login(self.admin)
        params = {'start_date': '2020-06-01', 'end_date': '2020-07-31'}
        page = self.client.get(reverse('credentialing_stats'), params)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['report']['rows'], report['rows'])
        self.assertNotContains(page, 'data-metrics-chart="credentialing-volume"')
        self.assertContains(page, 'data-metrics-chart="credentialing-flow"')
        export = self.client.get(reverse('credentialing_stats'), {**params, 'export': 'monthly'})
        self.assertEqual(list(csv.reader(StringIO(export.content.decode())))[-1],
                         ['2020-07', '', '0', '', '0', '', '', '0', '', '', 'Full month'])

    def test_credential_queue_and_repeated_applications_are_descriptive(self):
        from console.reporting import pending_credentials, credential_queue_rows, repeated_credentials
        CredentialApplication.objects.all().delete()
        pending = CredentialApplication.Status.PENDING
        self.credential(pending)
        self.credential(pending, reference_contact_datetime=self.when)
        self.credential(pending, reference_contact_datetime=self.when, reference_response_datetime=self.when)
        self.credential(CredentialApplication.Status.WITHDRAWN)
        rows = credential_queue_rows(pending_credentials(timezone.now()), timezone.now())
        self.assertEqual([r['status'] for r in rows], [
            'Awaiting reference contact', 'Awaiting reference response',
            'Awaiting processing after reference response',
        ])
        users = list(repeated_credentials(date(2020, 1, 1), date(2020, 12, 31)))
        self.assertEqual(len(users), 1)
        self.assertEqual((users[0]['total'], users[0]['pending'], users[0]['withdrawn']), (4, 3, 1))
        self.client.force_login(self.admin)
        response = self.client.get(reverse('credentialing_stats'), {'export': 'pending'})
        self.assertEqual(len(list(csv.DictReader(StringIO(response.content.decode())))), 3)

    def test_operational_exports_require_permission_and_valid_historical_dates(self):
        for view in ('credentialing_stats',):
            for export in ('monthly', 'pending', 'repeated', 'annual', 'stages', 'flow',
                           'queue-summary', 'reapplication-summary'):
                self.assertEqual(self.client.get(reverse(view), {'export': export}).status_code, 403)
            self.client.force_login(self.admin)
            response = self.client.get(reverse(view), {'start_date': 'bad', 'export': 'monthly'})
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('Content-Disposition', response)
            self.client.logout()

    def test_repeated_list_is_removed_and_existing_csv_still_exports_everyone(self):
        CredentialApplication.objects.all().delete()
        for index in range(21):
            user = User.objects.create_user(email=f'repeated-{index}@example.invalid', password=None,
                                            username=f'repeated-{index}')
            for attempt in range(3 if index == 20 else 2):
                app = CredentialApplication.objects.create(
                    user=user, slug=f'repeated-{index}-{attempt}', researcher_category=0,
                    status=CredentialApplication.Status.PENDING,
                )
                CredentialApplication.objects.filter(pk=app.pk).update(application_datetime=self.when)
        self.client.force_login(self.admin)
        url = reverse('credentialing_stats')
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        first = self.client.get(url, params)
        self.assertNotContains(first, 'Most applications per person within the selected period')
        self.assertNotIn('repeated', first.context)
        self.assertNotContains(first, 'Current pending credential applications')
        export = self.client.get(url, {**params, 'export': 'repeated', 'repeated_page': 2})
        self.assertEqual(len(list(csv.DictReader(StringIO(export.content.decode())))), 21)

    def test_credential_volume_empty_months_are_zero(self):
        from console.reporting import credential_flow_report
        report = credential_flow_report(date(2010, 1, 1), date(2010, 2, 28))
        self.assertEqual(report['chart']['labels'], ['2010-01', '2010-02'])
        for series in report['chart']['series']:
            self.assertEqual(series['values'], [0, 0])

    def test_annual_cohorts_close_and_keep_fractional_and_zero_durations(self):
        from console.reporting import credential_annual_stats
        CredentialApplication.objects.all().delete()
        for status in range(5):
            self.credential(status, decided=self.when + timezone.timedelta(hours=12),
                            reference_contact_datetime=self.when,
                            reference_response_datetime=self.when + timezone.timedelta(minutes=90))
        stats = credential_annual_stats()[2020]
        self.assertEqual(stats['count'], 5)
        self.assertEqual(sum(stats[key] for key in ('accepted', 'revoked', 'rejected', 'withdrawn', 'pending')), 5)
        self.assertEqual(stats['processed'], 3)
        self.assertEqual(stats['approved'], 66.67)
        self.assertEqual(stats['time_to_decision'], 0.5)
        self.assertEqual(stats['decision_observations'], 3)
        self.assertEqual(stats['time_to_ref'], 0)
        self.assertEqual(stats['time_to_reply'], 1.5)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('credentialing_stats'), {'export': 'annual'})
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual(rows[0]['Decision median days'], '0.5')
        self.assertEqual(rows[0]['Valid contact durations'], '5')

    def test_queue_age_summary_and_filters_use_application_age_boundaries(self):
        from console.reporting import credential_queue_summary, pending_credentials, filter_credential_queue
        CredentialApplication.objects.all().delete()
        now = self.when + timezone.timedelta(days=100)
        for days in (0, 6, 7, 29, 30, 89, 90):
            self.credential(0, submitted=now - timezone.timedelta(days=days))
        summary = credential_queue_summary(now)
        self.assertEqual(summary['rows'][0][1:], [2, 2, 2, 1, 7])
        self.assertEqual(summary['rows'][-1][1:], [2, 2, 2, 1, 7])
        queue = pending_credentials(now)
        for age, count in (('under7', 2), ('7to29', 2), ('30to89', 2), ('90plus', 1)):
            self.assertEqual(filter_credential_queue(queue, 'contact', age, now).count(), count)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('credentialing_stats'), {'queue_stage': 'invalid'})
        self.assertEqual(response.status_code, 200)

    def test_stage_durations_report_percentiles_missing_and_negative_pairs(self):
        from console.reporting import credential_stage_report
        CredentialApplication.objects.all().delete()
        self.credential(2, decided=self.when + timezone.timedelta(days=10),
                        reference_contact_datetime=self.when + timezone.timedelta(days=2),
                        reference_response_datetime=self.when + timezone.timedelta(days=3))
        self.credential(1, decided=self.when + timezone.timedelta(days=20),
                        reference_contact_datetime=self.when + timezone.timedelta(days=4))
        self.credential(2, decided=self.when + timezone.timedelta(days=2),
                        reference_contact_datetime=self.when - timezone.timedelta(days=1))
        report = credential_stage_report(date(2020, 1, 1), date(2020, 12, 31))
        self.assertEqual(report['rows'][0][1:], [2, 3.0, 3.8, 0, 1, 3, 66.67, 'Fewer than 10 observations'])
        self.assertEqual(report['rows'][1][1:], [1, 1.0, 1.0, 2, 0, 3, 33.33, 'Fewer than 10 observations'])
        self.assertEqual(report['rows'][2][1:], [1, 7.0, 7.0, 2, 0, 3, 33.33, 'Fewer than 10 observations'])
        self.client.force_login(self.admin)
        response = self.client.get(reverse('credentialing_stats'), {
            'start_date': '2020-01-01', 'end_date': '2020-12-31', 'export': 'stages'})
        self.assertEqual(len(list(csv.DictReader(StringIO(response.content.decode())))), 4)

    def test_inflow_and_decisions_use_different_event_dates(self):
        from console.reporting import credential_flow_report
        CredentialApplication.objects.all().delete()
        self.credential(2, submitted=timezone.make_aware(datetime(2019, 12, 1)), decided=self.when)
        self.credential(3, submitted=self.when, decided=self.when)
        self.credential(4, submitted=self.when, decided=self.when + timezone.timedelta(days=1))
        report = credential_flow_report(date(2020, 6, 1), date(2020, 7, 31))
        self.assertEqual(report['rows'], [
            ['2020-06', 2, 2, 0, 2, 'Full month'], ['2020-07', 0, 0, 0, 0, 'Full month'],
        ])
        self.client.force_login(self.admin)
        response = self.client.get(reverse('credentialing_stats'), {
            'start_date': '2020-06-01', 'end_date': '2020-07-31', 'export': 'flow'})
        self.assertEqual(list(csv.reader(StringIO(response.content.decode())))[0], report['headers'])

    def test_reapplication_summary_uses_complete_history_and_first_approval(self):
        from console.reporting import credential_reapplication_reports
        CredentialApplication.objects.all().delete()
        before = timezone.make_aware(datetime(2019, 12, 1))
        self.credential(1, submitted=before, decided=before + timezone.timedelta(days=1))
        self.credential(2, submitted=self.when, decided=self.when + timezone.timedelta(days=1))
        self.credential(1, submitted=self.when + timezone.timedelta(days=2),
                        decided=self.when + timezone.timedelta(days=3))
        other = CredentialApplication.objects.create(user=self.other, slug='summary-other', researcher_category=0,
                                                     status=0)
        CredentialApplication.objects.filter(pk=other.pk).update(application_datetime=self.when)
        reports = credential_reapplication_reports(date(2020, 1, 1), date(2020, 12, 31))
        self.assertEqual(reports[0]['rows'], [
            ['1 application', 1, 50.0], ['2 applications', 0, 0.0],
            ['3 applications', 1, 50.0], ['4+ applications', 0, 0.0],
        ])
        self.assertEqual(reports[1]['rows'][1], ['2 applications', 1, 50.0])
        self.assertEqual(reports[1]['rows'][4][1], 1)
        latest = {row[0]: row[1] for row in reports[2]['rows']}
        self.assertEqual(latest['Rejected'], 1)
        self.assertEqual(latest['Pending'], 1)
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        page = self.client.get(reverse('credentialing_stats'), params)
        self.assertContains(page, 'id="credential-queue"')
        self.assertContains(page, 'id="repeated-applications"', count=1)
        export = self.client.get(reverse('credentialing_stats'), {**params, 'export': 'reapplication-summary'})
        self.assertEqual(len(list(csv.DictReader(StringIO(export.content.decode())))), 15)

    def test_annual_year_boundary_uses_site_timezone_and_preserves_small_samples(self):
        from datetime import timezone as utc
        from console.reporting import credential_annual_stats
        CredentialApplication.objects.all().delete()
        submitted = datetime(2021, 1, 1, 2, tzinfo=utc.utc)
        self.credential(2, submitted=submitted, decided=submitted + timezone.timedelta(hours=12))
        with timezone.override('America/New_York'):
            stats = credential_annual_stats()
            self.assertEqual(list(stats), [2020])
            self.assertEqual(stats[2020]['decision_coverage'], 100.0)
            self.assertEqual(stats[2020]['contact_coverage'], 0.0)
            self.client.force_login(self.admin)
            page = self.client.get(reverse('credentialing_stats'))
        self.assertContains(page, 'Fewer than 10 observations')
        self.assertContains(page, 'n=1 / 1 eligible')
        self.assertContains(page, '100.00% coverage')
        self.assertContains(page, '0.50')
        self.assertContains(page, 'Years use the site time zone')

    def test_zero_eligible_observations_have_no_coverage_or_percentages(self):
        from console.reporting import credential_stage_report, credential_trend
        CredentialApplication.objects.all().delete()
        stages = credential_stage_report(date(2020, 1, 1), date(2020, 1, 31))
        for row in stages['rows']:
            self.assertEqual(row[1:], [0, None, None, 0, 0, 0, None, ''])
        monthly = credential_trend(date(2020, 1, 1), date(2020, 1, 31))
        self.assertEqual(monthly['rows'][0][5:10], [None, None, 0, None, None])

    def test_combined_volume_counts_invalid_decisions_without_changing_duration_sample(self):
        from console.reporting import credential_flow_report, credential_trend
        CredentialApplication.objects.all().delete()
        self.credential(2, decided=self.when - timezone.timedelta(seconds=1))
        self.credential(1, decided=self.when + timezone.timedelta(days=3))
        self.credential(4, decided=self.when + timezone.timedelta(days=7, seconds=1))
        flow = credential_flow_report(date(2020, 6, 1), date(2020, 6, 30))
        self.assertEqual(flow['chart']['type'], 'stacked-bar-line')
        self.assertEqual([(s['type'], s['values']) for s in flow['chart']['series']],
                         [('bar', [2]), ('bar', [1]), ('line', [3])])
        trend = credential_trend(date(2020, 6, 1), date(2020, 6, 30))
        self.assertEqual(trend['rows'][0][7:10], [2, 50.0, 50.0])

    def test_reapplication_history_and_period_counts_are_distinct(self):
        from console.reporting import credential_reapplication_reports, repeated_credentials
        CredentialApplication.objects.all().delete()
        self.credential(1, submitted=self.when - timezone.timedelta(days=365))
        self.credential(0, submitted=self.when)
        history = credential_reapplication_reports(date(2020, 1, 1), date(2020, 12, 31))
        self.assertEqual(history[0]['rows'][1], ['2 applications', 1, 100.0])
        self.assertEqual(repeated_credentials(date(2020, 1, 1), date(2020, 12, 31)).count(), 0)
