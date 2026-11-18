import copy
import csv
from datetime import date
from io import StringIO
from uuid import uuid4

from django.urls import reverse

from console.metrics_test_utils import MetricsTestCase
from project.models import PublishedAuthor, PublishedProject
from user.models import CredentialApplication, User


class TestSubmissionProfiles(MetricsTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.url = reverse('submission_stats')
        self.params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}

    def test_combined_page_and_legacy_link_have_nine_independent_charts(self):
        for params in (self.params, {**self.params, 'table': 'contributors'}):
            page = self.client.get(self.url, params)
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, 'data-metrics-chart=', count=9)
            self.assertContains(page, 'data-chart-downloads-for=', count=9)
            self.assertContains(page, 'Download data (CSV)', count=9)
            self.assertContains(page, 'Submission contributors')
            self.assertContains(page, 'metrics-chart-export.js')
            self.assertNotContains(page, 'Submission volumes ·')
            self.assertNotContains(page, 'Contributor profiles</a>')
            self.assertNotContains(page, '<details open')
            self.assertTrue(page.context['monthly_charts']['activity']['interactive_legend'])
            self.assertTrue(page.context['yearly_charts']['activity']['interactive_legend'])
            self.assertFalse(page.context['monthly_charts']['created']['legend'])
            html = page.content.decode()
            self.assertLess(html.index('submission-monthly-created'), html.index('submission-monthly-activity'))
            self.assertLess(html.index('submission-yearly-activity'), html.index('id="submission-contributors"'))
            self.assertLess(html.index('Submission metrics</div>'), html.index('id="submission-date-filters"'))
            self.assertLess(html.index('name="start_date"'), html.index('data-metrics-chart='))
            self.assertEqual(page.context['sections'][-1]['chart']['type'], 'pie')
            self.assertEqual(page.context['sections'][-1]['profile_id'], 'submission-profile-account-age')
            self.assertContains(page, 'aria-label="How Submission contributors is calculated"')
            self.assertNotIn('<p>Unique submitting authors of project versions', html)
            for section in page.context['sections']:
                if section['chart']['type'] == 'horizontal-bar':
                    self.assertEqual(section['chart']['row_height'], 40)

    def test_profile_csvs_match_chart_values_and_preserve_units(self):
        page = self.client.get(self.url, self.params)
        sections = page.context['sections']
        self.assertEqual(len(sections), 5)
        for section in sections:
            exported = self.client.get(self.url, {**self.params, 'export': 'contributor-data',
                                                  'section': section['profile_id']})
            self.assertEqual(exported.status_code, 200)
            rows = list(csv.DictReader(StringIO(exported.content.decode())))
            counts = {row['Metric']: int(row['Count']) for row in rows}
            self.assertTrue(all(row['Section'] == section['title'] for row in rows))
            if section['chart']['type'] == 'pie':
                for series in section['chart']['series']:
                    self.assertEqual(counts[series['name']], series['values'][0])
            else:
                self.assertEqual([counts[label] for label in section['chart']['labels']],
                                 section['chart']['series'][0]['values'])
        resource = next(s for s in sections if s['title'] == 'Submissions by resource type')
        self.assertEqual(resource['percentage_header'], 'Submitted versions (%)')
        self.assertIn('different populations', sections[0]['description'])

    def test_country_graph_top_ten_and_other_retains_all_countries_in_csv(self):
        for index, country in enumerate(('BR', 'CN', 'IN', 'JP', 'AU', 'NZ', 'CA', 'GB', 'DE', 'FR', 'ES', 'IT')):
            person = User.objects.create_user(f'profile-{index}@example.invalid', None, f'profile-{index}')
            CredentialApplication.objects.create(user=person, slug=f'profile-{index}', country=country,
                                                 researcher_category=0, status=CredentialApplication.Status.ACCEPTED)
            project = copy.copy(self.dataset)
            project.pk = None
            project.slug = f'profile-project-{index}'
            project.version = str(index)
            project.submission_slug = f'profile-{index}'
            project.public_project_uuid = uuid4()
            project.featured = None
            project.is_latest_version = False
            project.save()
            PublishedProject.objects.filter(pk=project.pk).update(submission_datetime=self.when)
            PublishedAuthor.objects.create(project=project, user=person, display_order=1, is_submitting=True)
        page = self.client.get(self.url, self.params)
        country = next(s for s in page.context['sections'] if s['title'] == 'Submitting authors by country')
        self.assertEqual(len(country['chart']['labels']), 11)
        self.assertEqual(country['chart']['labels'][-1], 'Other countries (3)')
        self.assertEqual(sum(country['chart']['series'][0]['values']), country['coverage_count'])
        response = self.client.get(self.url, {**self.params, 'export': 'contributor-data',
                                              'section': country['profile_id']})
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual(len([row for row in rows if row['Row type'] == 'category']), 13)
        self.assertTrue(all(not row['Metric'].startswith('Other countries') for row in rows))
        self.assertEqual(sum(int(row['Count']) for row in rows), country['coverage_total'])

    def test_permissions_invalid_dates_and_empty_cohort(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {'export': 'contributor-data'}).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url, {'export': 'contributor-data'}).status_code, 403)
        self.client.force_login(self.admin)
        bad = self.client.get(self.url, {'start_date': 'invalid'})
        self.assertEqual(bad.status_code, 400)
        self.assertContains(bad, 'Enter a valid date', status_code=400)
        self.assertEqual(self.client.get(self.url, {**self.params, 'export': 'contributor-data',
                                                    'section': 'unknown'}).status_code, 404)
        empty = self.client.get(self.url, {'start_date': '2010-01-01', 'end_date': '2010-12-31'})
        self.assertEqual(empty.status_code, 200)
        for section in empty.context['sections']:
            self.assertTrue(all(row['count'] == 0 for row in section['rows']))
