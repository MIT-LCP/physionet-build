import copy
import csv
from datetime import date, datetime
from io import StringIO
from uuid import uuid4
from unittest.mock import patch

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
from console.usage import submissions_metrics


class TestSubmissionsMetrics(MetricsTestCase):
    def metrics(self, start=date(2020, 1, 1), end=date(2020, 12, 31)):
        return {section['title']: section['rows'] for section in submissions_metrics(start, end)}

    def test_counts_submitting_authors_not_all_coauthors(self):
        metrics = self.metrics()
        overview = self.overview(metrics)
        self.assertEqual(overview['Submitted project versions'], 3)
        self.assertEqual(overview['Unique submitting authors'], 2)
        self.assertEqual(sum(row['count'] for row in metrics['Submissions by resource type']), 3)

    def test_missing_submitting_author_is_reported(self):
        self.active.authors.all().delete()
        overview = self.overview(self.metrics())
        self.assertEqual(overview['Submitted versions without a recorded submitting author'], 1)

    def test_active_copy_of_published_version_is_not_counted_twice(self):
        ActiveProject.objects.filter(pk=self.active.pk).update(
            core_project_id=self.dataset.core_project_id, version=self.dataset.version,
        )
        overview = self.overview(self.metrics())
        self.assertEqual(overview['Submitted project versions'], 2)
        self.assertEqual(overview['Unique submitting authors'], 1)

    def test_submission_contributors_are_separate_from_dataset_usage(self):
        self.client.force_login(self.admin)
        dates = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        with patch('console.views.usage_record_dates', return_value={'first': None, 'last': None}):
            usage = self.client.get(reverse('usage_stats'), dates)
        self.assertNotContains(usage, 'Submitting authors by country')
        self.assertNotContains(usage, 'Submitted project versions')
        url = reverse('submission_stats')
        params = {**dates, 'table': 'contributors'}
        page = self.client.get(url, params)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Submitting authors by country')
        self.assertNotContains(page, 'Most accessed datasets')
        self.assertContains(page, 'name="table" value="contributors"')
        export = self.client.get(url, {**params, 'export': 'csv'})
        self.assertEqual(export['Content-Disposition'], 'attachment; filename="submission-contributors-stats.csv"')
        text = export.content.decode()
        self.assertIn('Submitting authors by country', text)
        self.assertNotIn('Dataset viewers', text)
        self.client.logout()
        self.assertEqual(self.client.get(url, {**params, 'export': 'csv'}).status_code, 403)

    def test_contributor_demographics_show_coverage_and_keep_full_csv(self):
        self.client.force_login(self.admin)
        params = {'table': 'contributors', 'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        page = self.client.get(reverse('submission_stats'), params)
        sections = {s['title']: s for s in page.context['sections']}
        country = sections['Submitting authors by country']
        self.assertEqual((country['coverage_count'], country['coverage_total']), (1, 2))
        self.assertEqual(country['rows'][0]['percentage'], 50.0)
        self.assertEqual(country['rows'][0]['available_percentage'], 100.0)
        self.assertEqual(country['unavailable_rows'][0]['label'], 'No approved credential application')
        self.assertFalse(sections['Overview']['show_percentage'])
        self.assertContains(page, 'All submitting authors (%)')
        self.assertEqual(sections['Submissions by resource type']['percentage_header'], 'Submitted versions (%)')
        self.assertContains(page, '<summary>Definitions and limitations</summary>')
        self.assertNotContains(page, 'Access approvals cover contributor-reviewed requests')
        self.assertNotContains(page, 'Downloads by file')
        exported = self.client.get(reverse('submission_stats'), {**params, 'export': 'csv'})
        rows = list(csv.DictReader(StringIO(exported.content.decode())))
        self.assertIn('Percentage among submitting authors with information', rows[0])
        missing = next(row for row in rows if row['Metric'] == 'No approved credential application')
        self.assertEqual(missing['Percentage among submitting authors with information'], '')
