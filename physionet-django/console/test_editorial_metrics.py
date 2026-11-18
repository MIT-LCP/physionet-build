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


class TestEditorialMetrics(MetricsTestCase):
    def test_editorial_first_decision_is_unique_and_uses_decision_month(self):
        from console.reporting import editorial_trend
        from project.models import EditLog
        EditLog.objects.all().delete()
        ActiveProject.objects.exclude(pk=self.active.pk).update(submission_datetime=None)
        PublishedProject.objects.exclude(pk=self.dataset.pk).update(submission_datetime=None)
        # The active copy must not duplicate its published snapshot.
        ActiveProject.objects.filter(pk=self.active.pk).update(
            core_project_id=self.dataset.core_project_id, version=self.dataset.version,
        )
        first = EditLog.objects.create(project=self.dataset, decision=1,
                                       decision_datetime=self.when + timezone.timedelta(hours=36))
        EditLog.objects.create(project=self.dataset, decision=2,
                               decision_datetime=self.when + timezone.timedelta(days=10))
        EditLog.objects.create(project=self.active, decision=0,
                               decision_datetime=self.when + timezone.timedelta(days=5))
        report = editorial_trend(date(2020, 6, 1), date(2020, 7, 31))
        self.assertEqual(report['rows'], [['2020-06', 1.5, 1, 'Full month'], ['2020-07', None, 0, 'Full month']])
        self.assertNotIn('Excluded negative durations', report['description'])
        EditLog.objects.filter(pk=first.pk).update(decision_datetime=self.when - timezone.timedelta(days=1))
        report = editorial_trend(date(2020, 6, 1), date(2020, 7, 31))
        self.assertEqual(report['rows'][0], ['2020-06', None, 0, 'Full month'])
        self.assertIn('Excluded negative durations: 1', report['description'])

    def test_editorial_queue_reports_total_age_not_time_in_stage(self):
        from project.models import SubmissionStatus
        ActiveProject.objects.exclude(pk=self.active.pk).update(submission_datetime=None)
        ActiveProject.objects.filter(pk=self.active.pk).update(
            submission_status=SubmissionStatus.NEEDS_RESUBMISSION, is_on_hold=True,
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse('editorial_stats'), {'start_date': '2010-01-01', 'end_date': '2010-12-31'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['queue_total'], 1)
        row = response.context['queue_rows'][0]
        self.assertIn('on hold', row['status'])
        self.assertEqual(row['since'], self.when)
        self.assertNotContains(response, 'Current submitted projects')
        self.assertNotContains(response, 'Reporting period')
        export = self.client.get(reverse('editorial_stats'), {'export': 'pending'})
        self.assertEqual(len(list(csv.DictReader(StringIO(export.content.decode())))), 1)

    def test_editorial_monthly_export_matches_the_chart_table(self):
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        page = self.client.get(reverse('editorial_stats'), params)
        report = page.context['report']
        response = self.client.get(reverse('editorial_stats'), {**params, 'export': 'monthly'})
        rows = list(csv.reader(StringIO(response.content.decode())))
        expected = [report['headers'], *[
            ['' if value is None else str(value) for value in row] for row in report['rows']
        ]]
        self.assertEqual(rows, expected)

    def test_editorial_queue_paginates_five_projects_and_exports_the_full_queue(self):
        from project.models import SubmissionStatus
        ActiveProject.objects.update(submission_datetime=self.when, submission_status=SubmissionStatus.NEEDS_DECISION)
        total = ActiveProject.objects.count()
        self.assertGreater(total, 5)
        self.client.force_login(self.admin)
        url = reverse('editorial_stats')
        params = {'start_date': '2010-01-01', 'end_date': '2010-12-31'}
        first = self.client.get(url, params)
        self.assertEqual(first.context['queue_total'], total)
        self.assertEqual(len(first.context['queue_rows']), 5)
        self.assertTrue(first.context['queue_page'].has_next())
        second = self.client.get(url, {**params, 'page': 2})
        self.assertEqual(len(second.context['queue_rows']), min(5, total - 5))
        self.assertTrue({row['url'] for row in first.context['queue_rows']}.isdisjoint(
            row['url'] for row in second.context['queue_rows']))
        self.assertIn('start_date=2010-01-01', second.context['queue_query'])
        exported = self.client.get(url, {**params, 'page': 2, 'export': 'pending'})
        self.assertEqual(len(list(csv.DictReader(StringIO(exported.content.decode())))), total)

    def test_review_years_paginate_newest_first_while_chart_and_csv_keep_all_years(self):
        from project.models import EditLog
        EditLog.objects.all().delete()
        PublishedProject.objects.update(is_legacy=True)
        for year in range(1999, 2027):
            project = copy.copy(self.dataset)
            project.pk = None
            project.slug = f'review-year-{year}'
            project.version = str(year)
            project.submission_slug = f'review-year-{year}'
            project.public_project_uuid = uuid4()
            project.featured = None
            project.is_latest_version = False
            project.is_legacy = False
            project.publish_datetime = timezone.make_aware(datetime(year, 6, 15))
            project.submission_datetime = project.publish_datetime - timezone.timedelta(days=5)
            project.editor_assignment_datetime = project.publish_datetime - timezone.timedelta(days=3)
            project.save()
            PublishedProject.objects.filter(pk=project.pk).update(
                publish_datetime=timezone.make_aware(datetime(year, 6, 15)),
                submission_datetime=timezone.make_aware(datetime(year, 6, 10)),
                editor_assignment_datetime=timezone.make_aware(datetime(year, 6, 12)))
        self.client.force_login(self.admin)
        url = reverse('editorial_stats')
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        first = self.client.get(url, params)
        self.assertEqual(first.status_code, 200)
        self.assertEqual([year for year, _ in first.context['review_page']], [2026, 2025, 2024, 2023, 2022])
        self.assertEqual(first.context['review_page'].paginator.count, 28)
        self.assertContains(first, 'Showing 1–5 of 28 years, newest first.')
        self.assertContains(first, '<details>')
        self.assertNotContains(first, 'Reporting period')
        self.assertNotContains(first, 'Current submitted projects')
        self.assertContains(first, 'data-chart-downloads-for=', count=3)
        html = first.content.decode()
        publications_card = html[html.index('id="publications-by-year"'):html.index('id="time-to-review"')]
        self.assertIn('data-metrics-chart="editorial-annual-volume"', publications_card)
        self.assertNotIn('data-metrics-chart="editorial-annual-duration"', publications_card)
        review_card = html[html.index('id="time-to-review"'):]
        self.assertIn('data-metrics-chart="editorial-annual-duration"', review_card)
        self.assertNotIn('data-metrics-chart="editorial-annual-volume"', review_card)
        self.assertContains(first, 'Download data (CSV)', count=3)
        self.assertContains(first, 'Show annual table — all years')
        self.assertContains(first, 'Download all years (CSV)')
        self.assertIn('start_date=2020-01-01', first.context['review_links']['next_url'])
        self.assertTrue(first.context['review_links']['next_url'].endswith('#time-to-review'))
        last = self.client.get(url, {**params, 'review_page': 6})
        self.assertEqual([year for year, _ in last.context['review_page']], [2001, 2000, 1999])
        self.assertContains(last, '<details open>')
        self.assertNotIn('next_url', last.context['review_links'])
        charts = first.context['review_charts']
        self.assertEqual(charts['duration']['labels'], ['2020'])
        self.assertEqual(charts['duration']['series'][0]['values'], [2])
        self.assertEqual(charts['duration']['series'][1]['values'], [5])
        self.assertEqual(charts['duration']['series'][2]['values'], [None])
        exported = self.client.get(url, {**params, 'review_page': 6, 'export': 'csv'})
        rows = list(csv.DictReader(StringIO(exported.content.decode())))
        self.assertEqual(len(rows), 28)
        self.assertEqual([int(row['Year']) for row in rows], list(first.context['stats']))
        self.assertEqual([int(row['Total publications']) for row in rows], [1] * 28)
        filtered = self.client.get(url, {**params, 'export': 'review-period'})
        filtered_rows = list(csv.DictReader(StringIO(filtered.content.decode())))
        self.assertEqual([row['Year'] for row in filtered_rows], charts['volume']['labels'])
        self.assertEqual([int(row['Total publications']) for row in filtered_rows],
                         charts['volume']['series'][0]['values'])
        self.assertTrue(all(row['Start date'] == '2020-01-01' for row in filtered_rows))

    def test_review_years_empty_and_invalid_page_are_safe(self):
        from project.models import EditLog
        EditLog.objects.all().delete()
        PublishedProject.objects.update(is_legacy=True)
        self.client.force_login(self.admin)
        empty = self.client.get(reverse('editorial_stats'), {'review_page': 'bad'})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.context['review_page'].paginator.count, 0)
        self.assertEqual(empty.context['review_charts']['duration']['labels'], [])

    def test_exact_selected_dates_recompute_medians_and_keep_decision_cohorts_separate(self):
        from project.models import EditLog
        from console.editorial_annual import editorial_annual_stats
        from console.reporting import date_bounds
        EditLog.objects.all().delete()
        PublishedProject.objects.update(is_legacy=True)
        projects = []
        for index, (published_day, duration) in enumerate(((1, 10), (15, 4), (31, 30))):
            published = timezone.make_aware(datetime(2020, 6, 1)) + timezone.timedelta(days=published_day - 1)
            submitted = published - timezone.timedelta(days=duration)
            project = copy.copy(self.dataset)
            project.pk = None
            project.slug = f'period-review-{index}'
            project.version = str(index)
            project.submission_slug = f'period-review-{index}'
            project.public_project_uuid = uuid4()
            project.featured = None
            project.is_latest_version = False
            project.is_legacy = False
            project.save()
            PublishedProject.objects.filter(pk=project.pk).update(
                publish_datetime=published, submission_datetime=submitted,
                editor_assignment_datetime=submitted + timezone.timedelta(days=2))
            projects.append(project)
        for project, day in ((projects[0], 16), (projects[1], 14), (projects[1], 16), (projects[2], 17)):
            EditLog.objects.create(project=project, decision=1,
                                   decision_datetime=timezone.make_aware(datetime(2020, 6, day)))
        # A July publication can still have its first decision during the June filter.
        first, last = date_bounds(date(2020, 6, 15), date(2020, 6, 17))
        selected = editorial_annual_stats(first, last)
        self.assertEqual(selected[2020], [1, 2, 4, 20.5])
        self.assertEqual(editorial_annual_stats()[2020][:3], [3, 2, 10])
        self.client.force_login(self.admin)
        params = {'start_date': '2020-06-15', 'end_date': '2020-06-17'}
        page = self.client.get(reverse('editorial_stats'), params)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['review_charts']['duration']['series'][1]['values'], [4])
        self.assertEqual(page.context['review_charts']['duration']['series'][2]['values'], [20.5])
        self.assertEqual(page.context['review_charts']['duration']['partial'], [True])
        self.assertEqual(page.context['review_page'][0][1][0], 3)
        self.assertEqual(page.context['review_period_stats'][2020][0], 1)
        data = self.client.get(reverse('editorial_stats'), {**params, 'export': 'review-period'})
        row = next(csv.DictReader(StringIO(data.content.decode())))
        self.assertEqual(row['Total publications'], '1')
        self.assertEqual(row['Submission to final publication (median days)'], '4')
        self.assertEqual(row['End date'], '2020-06-17')
        self.client.logout()
        self.assertEqual(self.client.get(reverse('editorial_stats'), {'export': 'review-period'}).status_code, 403)
