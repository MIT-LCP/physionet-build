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
from console.usage import access_metrics


class TestAccessMetrics(MetricsTestCase):
    def metrics(self, start=date(2020, 1, 1), end=date(2020, 12, 31)):
        return {section['title']: section['rows'] for section in access_metrics(start, end)}

    def test_requests_and_approvals_use_distinct_users_and_different_dates(self):
        self.create_request(self.viewer)
        self.create_request(self.viewer, project=self.version, status=DataAccessRequest.REVOKED_VALUE)
        self.create_request(self.other, status=DataAccessRequest.REJECT_REQUEST_VALUE)
        self.create_request(self.coauthor, requested=timezone.make_aware(datetime(2019, 12, 31)))
        self.create_request(self.other, project=PublishedProject.objects.filter(resource_type_id=1).first())
        metrics = self.metrics()
        overview = self.overview(metrics)
        self.assertEqual(overview['Dataset access requests submitted'], 3)
        self.assertEqual(overview['Unique dataset access requesters'], 2)
        self.assertEqual(overview['Unique users approved for dataset access during selected dates'], 2)
        months = {row['label']: row['count'] for row in metrics['Dataset access requests by month']}
        self.assertEqual(len(months), 12)
        self.assertEqual(months['2020-06'], 3)
        self.assertEqual(months['2020-01'], 0)
        countries = {row['label']: row['count'] for row in metrics['Approved dataset users by country']}
        self.assertEqual(countries, {'United States of America': 1, 'No approved credential application': 1})

    def test_request_and_approval_date_boundaries(self):
        start = timezone.make_aware(datetime(2020, 1, 1))
        end = timezone.make_aware(datetime(2021, 1, 1))
        self.create_request(self.viewer, requested=start, decided=start)
        self.create_request(self.other, requested=end, decided=end)
        overview = self.overview(self.metrics())
        self.assertEqual(overview['Dataset access requests submitted'], 1)
        self.assertEqual(overview['Unique users approved for dataset access during selected dates'], 1)

    def test_request_page_is_separate_and_protected(self):
        self.create_request(self.viewer)
        url = reverse('access_request_stats')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url, {'export': 'csv'}).status_code, 403)
        self.client.force_login(self.admin)
        dates = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        access = self.client.get(url, dates)
        self.assertEqual(access.status_code, 200)
        self.assertContains(access, 'Approved dataset users by country')
        self.assertNotContains(access, 'Most accessed datasets')
        usage = self.client.get(reverse('usage_stats'), dates)
        self.assertNotContains(usage, 'Approved dataset users by country')
        export = self.client.get(url, {**dates, 'export': 'csv'})
        self.assertNotIn('Most accessed datasets', export.content.decode())
        self.assertIn('Approved dataset users', export.content.decode())

    def test_access_monthly_counts_use_event_dates_and_match_csv(self):
        from console.reporting import access_trend
        self.create_request(self.viewer, requested=self.when,
                            decided=timezone.make_aware(datetime(2020, 7, 1)))
        self.create_request(self.other, status=DataAccessRequest.REVOKED_VALUE)
        self.create_request(self.coauthor, status=DataAccessRequest.REJECT_REQUEST_VALUE)
        report = access_trend(date(2020, 6, 15), date(2020, 8, 1))
        self.assertEqual(report['rows'], [
            ['2020-06', 3, 1, 1, 'Partial month'], ['2020-07', 0, 1, 0, 'Full month'],
            ['2020-08', 0, 0, 0, 'Partial month'],
        ])
        self.client.force_login(self.admin)
        params = {'start_date': '2020-06-15', 'end_date': '2020-08-01'}
        page = self.client.get(reverse('access_request_stats'), params)
        self.assertEqual(page.context['report'], report)
        response = self.client.get(reverse('access_request_stats'), {**params, 'export': 'monthly'})
        rows = list(csv.reader(StringIO(response.content.decode())))
        self.assertEqual(rows, [report['headers'], *[[str(cell) for cell in row] for row in report['rows']]])
        self.assertContains(page, 'Boundary months cover only selected dates')

    def test_current_access_queue_ignores_historical_dates_and_excludes_closed_requests(self):
        self.create_request(self.viewer, status=DataAccessRequest.PENDING_VALUE)
        self.create_request(self.other, status=DataAccessRequest.REJECT_REQUEST_VALUE)
        self.client.force_login(self.admin)
        url = reverse('access_request_stats')
        response = self.client.get(url, {'start_date': '2010-01-01', 'end_date': '2010-12-31'})
        self.assertEqual(response.context['queue_total'], 1)
        row = response.context['queue_rows'][0]
        self.assertEqual(row['since'], self.when)
        self.assertEqual(row['days'], (timezone.now() - self.when).days)
        self.assertContains(response, 'not filtered by the selected historical dates')
        export = self.client.get(url, {'export': 'pending'})
        rows = list(csv.DictReader(StringIO(export.content.decode())))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Elapsed days (floor)'], str(row['days']))

    def test_access_queue_paginates_but_exports_all_pending_requests(self):
        DataAccessRequest.objects.bulk_create([
            DataAccessRequest(requester=self.viewer, project=self.dataset, status=DataAccessRequest.PENDING_VALUE)
            for _ in range(51)
        ])
        self.client.force_login(self.admin)
        url = reverse('access_request_stats')
        first = self.client.get(url)
        self.assertEqual(len(first.context['queue_rows']), 5)
        self.assertEqual(first.context['queue_total'], 51)
        second = self.client.get(url, {'page': 11})
        self.assertEqual(len(second.context['queue_rows']), 1)
        export = self.client.get(url, {'export': 'pending'})
        self.assertEqual(len(list(csv.DictReader(StringIO(export.content.decode())))), 51)

    def test_access_country_pagination_preserves_queue_page_and_exports_all_countries(self):
        from unittest.mock import patch
        from urllib.parse import parse_qs, urlsplit
        sections = [{'title': 'Approved dataset users by country', 'description': '', 'rows': [
            {'label': f'Country {i}', 'count': 1, 'percentage': 100 / 7} for i in range(7)
        ]}]
        self.client.force_login(self.admin)
        url = reverse('access_request_stats')
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31', 'page': 2, 'show_all_countries': 1}
        with patch('console.views.access_metrics', return_value=sections):
            first = self.client.get(url, params)
            country = first.context['sections'][0]
            self.assertEqual(len(country['rows']), 5)
            link = urlsplit(country['next_url'])
            self.assertEqual(link.fragment, 'approved-users-by-country')
            query = parse_qs(link.query)
            self.assertEqual(query['page'], ['2'])
            self.assertEqual(query['country_page'], ['2'])
            self.assertEqual(query['start_date'], ['2020-01-01'])
            self.assertEqual(query['end_date'], ['2020-12-31'])
            self.assertNotIn('export', query)
            second = self.client.get(url, {**params, 'country_page': 2})
            self.assertEqual(len(second.context['sections'][0]['rows']), 2)
            self.assertIn('country_page=2', second.context['queue_query'])
            exported = self.client.get(url, {**params, 'country_page': 2, 'export': 'csv'})
            self.assertEqual(len(list(csv.DictReader(StringIO(exported.content.decode())))), 7)

    def test_access_queue_summary_age_boundaries_versions_and_distinct_people(self):
        from console.reporting import access_pending_summary, access_pending_summary_csv
        DataAccessRequest.objects.all().delete()
        other_dataset = copy.copy(self.dataset)
        other_dataset.pk = None
        other_dataset.slug = 'demoselfmanaged'
        other_dataset.version = 'queue-test'
        other_dataset.submission_slug = 'queue-test'
        other_dataset.public_project_uuid = uuid4()
        other_dataset.featured = None
        other_dataset.is_latest_version = False
        other_dataset.save()
        now = self.when
        ages = [0, 7 - 1 / 86400, 7, 30 - 1 / 86400, 30, 90 - 1 / 86400, 90, 365 - 1 / 86400, 365, 400]
        for index, age in enumerate(ages):
            self.create_request(self.viewer, project=self.dataset if index % 2 else self.version,
                                status=DataAccessRequest.PENDING_VALUE,
                                requested=now - timezone.timedelta(days=age))
        self.create_request(self.viewer, project=other_dataset, status=0, requested=now - timezone.timedelta(days=8))
        self.create_request(self.other, project=other_dataset, status=0, requested=now - timezone.timedelta(days=10))
        self.create_request(self.other, status=0, requested=now + timezone.timedelta(seconds=1))
        self.create_request(self.other, status=3, requested=now - timezone.timedelta(days=20))
        report = access_pending_summary(DataAccessRequest.objects.select_related('project'), now)
        self.assertEqual(report['total']['cells'][:2], [12, 2])
        self.assertEqual(report['total']['cells'][4:], [2, 4, 2, 2, 2])
        self.assertEqual(sum(row['cells'][0] for row in report['datasets']), 12)
        self.assertEqual(sum(row['cells'][1] for row in report['datasets']), 3)
        first = report['datasets'][0]
        self.assertEqual(first['cells'][:2], [10, 1])
        self.assertAlmostEqual(first['cells'][2], 60.0, places=4)
        self.assertEqual(first['cells'][3], 400.0)
        self.assertEqual(len(first['versions']), 2)
        self.assertEqual(sum(row['cells'][1] for row in first['versions']), 2)
        self.assertEqual(report['datasets'][1]['label'], 'demoselfmanaged')
        for dataset in report['datasets']:
            self.assertEqual(sum(dataset['cells'][4:]), dataset['cells'][0])
            self.assertEqual(sum(v['cells'][0] for v in dataset['versions']), dataset['cells'][0])
        for versions, count in ((False, 2), (True, 3)):
            response = access_pending_summary_csv(report, versions=versions)
            rows = list(csv.DictReader(StringIO(response.content.decode())))
            self.assertEqual(len(rows), count + (not versions))
            detail = [row for row in rows if row['Row type'] != 'total']
            self.assertEqual(sum(int(row['Pending requests']) for row in detail), 12)
            if not versions:
                self.assertEqual(rows[-1]['Row type'], 'total')
                self.assertEqual(int(rows[-1]['Unique requesters']), 2)
            self.assertEqual({row['Snapshot'] for row in rows}, {now.isoformat()})

    def test_access_summary_empty_queue(self):
        from console.reporting import access_pending_summary, access_pending_summary_csv
        summary = access_pending_summary([], self.when)
        self.assertEqual(summary['datasets'], [])
        self.assertEqual(summary['total']['cells'], [0, 0, None, None, 0, 0, 0, 0, 0])
        for versions in (False, True):
            rows = list(csv.DictReader(StringIO(access_pending_summary_csv(summary, versions).content.decode())))
            self.assertEqual(len(rows), 0 if versions else 1)
            if not versions:
                self.assertEqual(rows[0]['Row type'], 'total')
                self.assertEqual(rows[0]['Pending requests'], '0')

    def test_access_queue_summary_shows_ten_datasets_and_current_exports_ignore_dates(self):
        from unittest.mock import patch
        DataAccessRequest.objects.all().delete()
        for index in range(11):
            project = copy.copy(self.dataset)
            project.pk = None
            project.slug = f'queue-ds-{index}'
            project.version = f'queue-{index}'
            project.submission_slug = f'queue-{index}'
            project.public_project_uuid = uuid4()
            project.featured = None
            project.is_latest_version = False
            project.save()
            self.create_request(self.viewer, project=project, status=0, requested=self.when)
        self.client.force_login(self.admin)
        url = reverse('access_request_stats')
        params = {'start_date': '2010-01-01', 'end_date': '2010-12-31'}
        with patch('console.views.timezone.now', return_value=self.when):
            page = self.client.get(url, params)
            self.assertEqual(page.context['queue_total'], 11)
            self.assertContains(page, 'Showing 1–5 of 11')
            last = self.client.get(url, {**params, 'page': 3})
            self.assertContains(last, 'Showing 11–11 of 11')
            self.assertEqual(len(page.context['queue_rows']), 5)
            self.assertEqual(page.context['access_summary']['total']['cells'][0], 11)
            self.assertEqual(page.context['access_summary']['snapshot'], page.context['queue_now'])
            self.assertEqual(len(page.context['access_summary_rows']), 10)
            self.assertContains(page, 'View all datasets')
            full = self.client.get(url, {**params, 'show_all_datasets': 1})
            self.assertEqual(len(full.context['access_summary_rows']), 11)
            for export in ('pending-datasets', 'pending-versions'):
                response = self.client.get(url, {'start_date': 'invalid', 'export': export})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(list(csv.DictReader(StringIO(response.content.decode())))),
                                 12 if export == 'pending-datasets' else 11)
        self.client.logout()
        for export in ('pending-datasets', 'pending-versions'):
            self.assertEqual(self.client.get(url, {'export': export}).status_code, 403)

    def test_access_decisions_are_separate_from_unique_approved_users_and_coverage(self):
        self.create_request(self.viewer, status=3)
        self.create_request(self.viewer, project=self.version, status=4)
        self.create_request(self.other, status=1)
        self.create_request(self.coauthor, status=3)
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        url = reverse('access_request_stats')
        page = self.client.get(url, params)
        sections = {s['title']: s for s in page.context['sections']}
        overview = {row['label']: row['count'] for row in sections['Overview']['rows']}
        self.assertEqual(overview['Dataset access approvals recorded'], 3)
        self.assertEqual(overview['Dataset access rejections recorded'], 1)
        self.assertEqual(overview['Unique users approved for dataset access during selected dates'], 2)
        self.assertFalse(sections['Overview']['show_percentage'])
        countries = sections['Approved dataset users by country']
        self.assertEqual((countries['coverage_count'], countries['coverage_total']), (1, 2))
        self.assertEqual(countries['rows'][0]['percentage'], 50.0)
        self.assertEqual(countries['rows'][0]['available_percentage'], 100.0)
        self.assertEqual(countries['unavailable_rows'][0]['label'], 'No approved credential application')
        self.assertContains(page, 'All approved users (%)')
        self.assertContains(page, '<summary>Definitions and limitations</summary>')
        self.assertNotContains(page, 'Viewers, approved users and submitting authors are different populations.')
        exported = self.client.get(url, {**params, 'export': 'csv'})
        rows = list(csv.DictReader(StringIO(exported.content.decode())))
        self.assertIn('Percentage among approved users with information', rows[0])
        missing = next(row for row in rows if row['Metric'] == 'No approved credential application')
        self.assertEqual(missing['Percentage among approved users with information'], '')
        self.assertEqual(missing['Row type'], 'unavailable')
        country_rows = [row for row in rows if row['Section'] == 'Approved dataset users by country']
        self.assertEqual([row['Row type'] for row in country_rows], ['category', 'unavailable'])

    def test_access_summary_age_format_links_highlights_and_shared_coverage_notice(self):
        self.create_request(self.viewer, status=0, requested=self.when - timezone.timedelta(days=90))
        self.create_request(self.viewer, status=3)
        self.create_request(self.coauthor, status=3)
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-06-15'}
        from unittest.mock import patch
        with patch('console.views.timezone.now', return_value=self.when):
            page = self.client.get(reverse('access_request_stats'), params)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, '<td>90.0</td>')
        self.assertContains(page, 'Snapshot:', count=1)
        self.assertContains(page, '<td>March 17, 2020</td>')
        self.assertContains(page, 'scope="row" class="text-nowrap"')
        from django.template.loader import render_to_string
        cells = render_to_string('console/access_age_cells.html', {'cells': [1, 1, 0.1, 0.1, 0, 0, 0, 0, 0]})
        self.assertEqual(cells.count('class="text-muted"'), 5)
        self.assertNotIn('table-warning', cells)
        self.assertContains(page, 'class="table-warning"')
        self.assertContains(page, '<td class="text-muted">0</td>')
        self.assertContains(page, '<td class="table-warning">1</td>')
        self.assertTrue(page.context['queue_hide_status'])
        self.assertEqual({row['status'] for row in page.context['queue_rows']}, {'Pending access review'})
        self.assertNotContains(page, '<th>Status</th>')
        self.assertContains(page, 'completed 24-hour days (floor)')
        self.assertContains(page, 'Download period summary CSV')
        self.assertContains(page, 'action="#access-period"')
        html = page.content.decode()
        self.assertLess(html.index('id="current-access-queue"'), html.index('id="access-period"'))
        self.assertLess(html.index('id="access-period"'), html.index('name="start_date"'))
        self.assertLess(html.index('id="access-period"'), html.index('>Overview'))

        self.assertContains(page, reverse('published_projects_by_slug', args=[self.dataset.slug]))
        self.assertContains(page, reverse('manage_published_project', args=[self.dataset.slug, self.dataset.version]))
        self.assertContains(page, 'Not filtered by the selected dates.')
        self.assertNotContains(page, 'Showing 1 of 1 datasets')
        sections = {section['title']: section for section in page.context['sections']}
        self.assertEqual(sections['Approved dataset users by researcher category']['coverage_reference'],
                         'Approved dataset users by country')
        self.assertContains(page, 'Approved users without available information', count=1)
        # Equal missing-field counts alone do not prove the missing groups contain the same people.
        CredentialApplication.objects.filter(user=self.viewer, status=2).update(country='ZZ', researcher_category=99)
        other = self.client.get(reverse('access_request_stats'), params)
        categories = next(section for section in other.context['sections']
                          if section['title'] == 'Approved dataset users by researcher category')
        self.assertNotIn('coverage_reference', categories)

    def test_access_age_display_and_csv_round_original_value_independently(self):
        from console.reporting import access_pending_summary, access_pending_summary_csv
        from django.template.loader import render_to_string
        from datetime import timezone as dt_timezone
        now = self.when.astimezone(dt_timezone.utc)
        self.create_request(self.viewer, status=0, requested=now - timezone.timedelta(days=159.449))
        summary = access_pending_summary(DataAccessRequest.objects.select_related('project'), now)
        self.assertAlmostEqual(summary['total']['cells'][2], 159.449)
        html = render_to_string('console/access_age_cells.html', {'cells': summary['total']['cells']})
        self.assertIn('<td>159.4</td>', html)
        rows = list(csv.DictReader(StringIO(access_pending_summary_csv(summary).content.decode())))
        self.assertEqual(rows[-1]['Median age (days)'], '159.45')

    def test_access_queue_csv_is_reproducible_from_snapshot(self):
        from datetime import datetime
        self.create_request(self.viewer, status=0, requested=self.when)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('access_request_stats'), {'export': 'pending'})
        row = next(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual(row['Dataset'], self.dataset.slug)
        self.assertEqual(row['Version'], self.dataset.version)
        elapsed = datetime.fromisoformat(row['Snapshot']) - datetime.fromisoformat(row['Since'])
        self.assertEqual(int(row['Elapsed days (floor)']), elapsed.days)
