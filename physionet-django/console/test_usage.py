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


class TestUsageMetrics(MetricsTestCase):
    def test_unique_viewers_and_dataset_versions_are_deduplicated(self):
        metrics = self.metrics()
        overview = self.overview(metrics)
        self.assertEqual(overview['Unique registered dataset viewers'], 2)
        self.assertEqual(overview['Datasets accessed (versions combined)'], 1)
        self.assertEqual(metrics['Most accessed datasets'], [
            {'label': self.dataset.slug, 'count': 2, 'percentage': 100.0},
        ])

    def test_latest_approved_credential_and_missing_demographics(self):
        metrics = self.metrics()
        countries = {row['label']: row for row in metrics['Dataset viewers by country']}
        self.assertEqual(countries['United States of America']['count'], 1)
        self.assertEqual(countries['No approved credential application']['percentage'], 50)
        self.assertEqual(countries['United States of America']['available_percentage'], 100)
        self.assertIsNone(countries['No approved credential application']['available_percentage'])
        categories = {row['label']: row['count'] for row in metrics['Dataset viewers by researcher category']}
        self.assertEqual(categories, {'Industry Researcher': 1, 'No approved credential application': 1})
        self.assertEqual(self.overview(metrics)['Viewers with an approved credential application'], 1)

    def test_course_use_is_declared_in_latest_approved_credential(self):
        rows = {row['label']: row['count'] for row in self.metrics()['Declared course use']}
        self.assertEqual(rows, {'I am taking a course using the data': 1, 'No approved credential application': 1})

    def test_excludes_other_content_types_and_orphaned_logs(self):
        self.create_log(self.active, self.coauthor, self.when)
        AccessLog.objects.create(
            user=self.coauthor, content_type=ContentType.objects.get_for_model(PublishedProject), object_id=99999999,
        )
        self.assertEqual(self.overview(self.metrics())['Unique registered dataset viewers'], 2)

    def test_excludes_software_access(self):
        software = PublishedProject.objects.filter(resource_type_id=1).first()
        self.assertIsNotNone(software)
        self.create_log(software, self.coauthor, self.when)
        self.assertEqual(self.overview(self.metrics())['Unique registered dataset viewers'], 2)

    def test_empty_date_range_is_safe(self):
        metrics = self.metrics(date(2010, 1, 1), date(2010, 12, 31))
        self.assertTrue(all(count == 0 for count in self.overview(metrics).values()))
        for title, rows in metrics.items():
            if title != 'Overview':
                self.assertEqual(rows, [])

    def test_date_boundaries_and_overlapping_log_sessions(self):
        AccessLog.objects.all().delete()
        start = timezone.make_aware(datetime(2020, 1, 1))
        end = timezone.make_aware(datetime(2021, 1, 1))
        self.create_log(self.dataset, self.viewer, start - timezone.timedelta(minutes=1), start)
        self.create_log(self.dataset, self.other, end - timezone.timedelta(microseconds=1))
        self.create_log(self.dataset, self.coauthor, end)
        self.assertEqual(self.overview(self.metrics())['Unique registered dataset viewers'], 2)

    def test_query_count_does_not_grow_with_number_of_viewers(self):
        # Warm the ContentType cache before comparing query counts.
        self.metrics()
        with CaptureQueriesContext(connection) as before:
            self.metrics()
        self.create_log(self.dataset, self.coauthor, self.when)
        with CaptureQueriesContext(connection) as after:
            self.metrics()
        self.assertEqual(len(before), len(after))
        self.assertLess(len(after), 65)

    def test_version_viewers_are_deduplicated_within_each_version(self):
        rows = {row['label']: row['count'] for row in self.metrics()['Registered viewers by dataset version']}
        self.assertEqual(rows, {
            f'{self.dataset.slug} / {self.dataset.version}': 1,
            f'{self.version.slug} / {self.version.version}': 2,
        })

    def test_institution_names_are_normalized_without_guessing_aliases(self):
        CredentialApplication.objects.filter(user=self.viewer).update(organization_name='  Example   University ')
        CredentialApplication.objects.create(
            user=self.other, slug='usage-other-cred', country='BR', researcher_category=0,
            status=CredentialApplication.Status.ACCEPTED, organization_name='example university',
        )
        overview = self.overview(self.metrics())
        self.assertEqual(overview['Distinct declared institution names among viewers'], 1)
        CredentialApplication.objects.filter(user=self.other).update(organization_name='EU')
        overview = self.overview(self.metrics())
        self.assertEqual(overview['Distinct declared institution names among viewers'], 2)

    def test_new_and_existing_accounts_are_relative_to_selected_dates(self):
        User.objects.filter(pk=self.viewer.pk).update(join_date=date(2020, 1, 1))
        User.objects.filter(pk=self.other.pk).update(join_date=date(2019, 12, 31))
        self.create_request(self.viewer)
        self.create_request(self.other)
        for title in ('Dataset viewers by account age',):
            rows = self.metrics()[title]
            self.assertEqual([row['count'] for row in rows], [1, 1])
            self.assertEqual([row['percentage'] for row in rows], [50, 50])

    def test_accounts_created_after_historical_period_are_not_labeled_new(self):
        User.objects.filter(pk__in=[self.viewer.pk, self.other.pk]).update(join_date=date(2021, 1, 1))
        rows = self.metrics()['Dataset viewers by account age']
        self.assertEqual([row['count'] for row in rows], [0, 0, 2])
        self.assertEqual(rows[-1]['label'], 'Not available (account created after selected dates)')

    def test_page_export_and_navigation_order(self):
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        url = reverse('usage_stats')
        page = self.client.get(url, params)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Download CSV')
        self.assertContains(page, 'does not measure confirmed downloads')
        html = page.content.decode()
        self.assertLess(html.index('id="nav_submission_stats"'), html.index('id="nav_usage_stats"'))
        self.assertLess(html.index('id="nav_usage_stats"'), html.index('id="nav_downloads"'))
        self.assertContains(page, 'value="2020-01-01"')

        response = self.client.get(url, {**params, 'export': 'csv'})
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="usage-stats.csv"')
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        expected = [
            (section['title'], row['label'], str(row['count']),
             '' if row['percentage'] is None else str(row['percentage']))
            for section in usage_sections(
                usage_metrics(date(2020, 1, 1), date(2020, 12, 31)), 'usage')
            for row in sorted(section['rows'], key=lambda row: not row.get('information_available', True))
        ]
        self.assertEqual([(row['Section'], row['Metric'], row['Count'], row['Percentage']) for row in rows], expected)
        self.assertTrue(all(row['Start date'] == params['start_date'] for row in rows))
        self.assertNotIn(self.viewer.email, response.content.decode())

    def test_invalid_dates_rejected_for_page_and_export(self):
        self.client.force_login(self.admin)
        for params in (
            {'start_date': 'not-a-date'},
            {'start_date': '2020-12-31', 'end_date': '2020-01-01'},
            {'end_date': '9999-12-31'},
        ):
            for export in ('', 'csv'):
                with self.subTest(params=params, export=export):
                    response = self.client.get(reverse('usage_stats'), {**params, 'export': export})
                    self.assertEqual(response.status_code, 400)
                    self.assertNotIn('Content-Disposition', response)

    def test_access_and_export_require_stats_permission(self):
        for user in (None, self.other):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for params in ({}, {'export': 'csv'}):
                with self.subTest(user=user, params=params):
                    self.assertEqual(self.client.get(reverse('usage_stats'), params).status_code, 403)

    def test_usage_tables_paginate_independently_and_export_all_rows(self):
        from unittest.mock import patch
        from urllib.parse import parse_qs, urlsplit
        sections = [
            {'title': title, 'description': '', 'rows': [
                {'label': f'{prefix}-{index}', 'count': index + 1, 'percentage': None}
                for index in range(count)
            ]}
            for title, prefix, count in (
                ('Most accessed datasets', 'dataset', 20),
                ('Dataset viewers by country', 'country', 7),
                ('Registered viewers by dataset version', 'version', 11),
            )
        ]
        self.client.force_login(self.admin)
        url = reverse('usage_stats')
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        with patch('console.views.usage_metrics', return_value=sections):
            first = self.client.get(url, params)
            self.assertEqual([len(s['rows']) for s in first.context['sections']], [7, 11, 20])
            self.assertEqual(first.context['sections'][-1]['title'], 'Most accessed datasets')
            second = self.client.get(url, {**params, 'country_page': 2, 'version_page': 2, 'dataset_page': 4})
            countries, versions, datasets = second.context['sections']
            self.assertEqual([r['label'] for r in datasets['rows']], [f'dataset-{i}' for i in range(20)])
            self.assertNotIn('page', datasets)
            self.assertNotIn('next_url', datasets)
            self.assertEqual([r['label'] for r in countries['rows']], ['country-5', 'country-6'])
            self.assertEqual([r['label'] for r in versions['rows']], [f'version-{i}' for i in range(5, 10)])
            link = urlsplit(versions['next_url'])
            self.assertEqual(link.fragment, 'viewers-by-version')
            query = parse_qs(link.query)
            self.assertEqual(query['country_page'], ['2'])
            self.assertEqual(query['version_page'], ['3'])
            self.assertEqual(query['dataset_page'], ['4'])
            self.assertEqual(query['start_date'], ['2020-01-01'])
            self.assertEqual(query['end_date'], ['2020-12-31'])
            self.assertNotIn('export', query)
            self.assertContains(second, 'id="viewers-by-country"')
            self.assertContains(second, 'id="viewers-by-version"')
            self.assertContains(second, 'Top 20 datasets by unique registered viewers')
            last = self.client.get(url, {**params, 'version_page': 3, 'country_page': 'invalid'})
            self.assertEqual([len(s['rows']) for s in last.context['sections']], [5, 1, 20])
            exported = self.client.get(url, {**params, 'country_page': 2, 'version_page': 3, 'export': 'csv'})
            rows = list(csv.DictReader(StringIO(exported.content.decode())))
            self.assertEqual(len(rows), 38)
            self.assertEqual(sum(row['Section'] == 'Dataset viewers by country' for row in rows), 7)
            self.assertEqual(sum(row['Section'] == 'Registered viewers by dataset version' for row in rows), 11)
            self.assertEqual(sum(row['Section'] == 'Most accessed datasets' for row in rows), 20)

    def test_viewer_demographics_separate_missing_information_and_show_both_denominators(self):
        CredentialApplication.objects.create(
            user=self.other, slug='usage-missing', status=CredentialApplication.Status.ACCEPTED,
            country='ZZ', researcher_category=99,
        )
        self.create_log(self.dataset, self.coauthor, self.when)
        sections = {s['title']: s for s in usage_metrics(date(2020, 1, 1), date(2020, 12, 31))}
        for name in ('Dataset viewers by country', 'Dataset viewers by researcher category'):
            section = sections[name]
            self.assertEqual(section['coverage_count'], 1)
            self.assertEqual(section['coverage_total'], 3)
            self.assertEqual(section['coverage_percentage'], 33.33)
            rows = {row['label']: row for row in section['rows']}
            self.assertEqual(rows['No approved credential application']['count'], 1)
            self.assertEqual(rows['Information missing or unrecognized']['count'], 1)
            self.assertEqual(sum(row['count'] for row in rows.values()), 3)
            for label in ('No approved credential application', 'Information missing or unrecognized'):
                self.assertEqual(rows[label]['percentage'], 33.33)
                self.assertIsNone(rows[label]['available_percentage'])
        country = {row['label']: row for row in sections['Dataset viewers by country']['rows']}
        self.assertEqual(country['United States of America']['available_percentage'], 100.0)
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        page = self.client.get(reverse('usage_stats'), params)
        self.assertContains(page, 'With information (%)')
        self.assertContains(page, 'Information missing or unrecognized')
        exported = self.client.get(reverse('usage_stats'), {**params, 'export': 'csv'})
        country_rows = [row for row in csv.DictReader(StringIO(exported.content.decode()))
                        if row['Section'] == 'Dataset viewers by country']
        missing = next(row for row in country_rows if row['Metric'] == 'Information missing or unrecognized')
        self.assertEqual(missing['Percentage among viewers with information'], '')
        self.assertEqual(missing['Viewers with information'], '1')
        self.assertEqual(missing['Total viewers'], '3')
        self.assertEqual(missing['Coverage (%)'], '33.33')

    def test_no_known_viewer_information_has_no_conditional_percentage(self):
        from console.usage import _demographics, _viewer_demographic
        empty = _viewer_demographic(_demographics(User.objects.none()), 'credential_country', {'US': 'US'}, 'Country')
        self.assertEqual(empty['rows'], [])
        self.assertIsNone(empty['coverage_percentage'])
        missing = _viewer_demographic(
            _demographics(User.objects.filter(pk=self.other.pk)), 'credential_country', {'US': 'US'}, 'Country')
        self.assertEqual(missing['coverage_percentage'], 0.0)
        self.assertIsNone(missing['rows'][0]['available_percentage'])

    def test_usage_screen_hides_course_use_and_empty_percentage_columns_but_csv_keeps_course(self):
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        page = self.client.get(reverse('usage_stats'), params)
        self.assertNotContains(page, 'Declared course use')
        self.assertContains(page, '<summary>Definitions and limitations</summary>')
        sections = {section['title']: section for section in page.context['sections']}
        self.assertFalse(sections['Overview']['show_percentage'])
        self.assertFalse(sections['Registered viewers by dataset version']['show_percentage'])
        self.assertEqual(sections['Dataset viewers by country']['label_header'], 'Country')
        self.assertEqual(sections['Dataset viewers by researcher category']['label_header'], 'Researcher category')
        versions = sections['Registered viewers by dataset version']['rows']
        self.assertEqual([row['count'] for row in versions], [2, 1])
        exported = self.client.get(reverse('usage_stats'), {**params, 'export': 'csv'})
        self.assertContains(exported, 'Declared course use')

    def test_usage_country_summary_keeps_missing_groups_separate_and_csv_complete(self):
        from unittest.mock import patch
        from urllib.parse import parse_qs, urlsplit
        country_rows = [
            {'label': f'Country {i}', 'count': 12 - i, 'percentage': round(100 * (12 - i) / 83, 2),
             'available_percentage': round(100 * (12 - i) / 78, 2), 'information_available': True}
            for i in range(12)
        ]
        unavailable = {'label': 'No approved credential application', 'count': 5, 'percentage': 6.02,
                       'available_percentage': None, 'information_available': False}
        sections = [
            {'title': 'Dataset viewers by country', 'description': '', 'rows': [unavailable, *country_rows],
             'coverage_count': 78, 'coverage_total': 83, 'coverage_percentage': 93.98},
            {'title': 'Registered viewers by dataset version', 'description': '', 'rows': [
                {'label': f'dataset / {i}', 'count': 25 - i, 'percentage': None} for i in range(25)]},
        ]
        self.client.force_login(self.admin)
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        url = reverse('usage_stats')
        with patch('console.views.usage_metrics', return_value=sections):
            page = self.client.get(url, params)
            countries, versions = page.context['sections']
            self.assertEqual(len(countries['rows']), 11)
            self.assertEqual(countries['rows'][-1], {
                'label': 'Other countries (2)', 'count': 3, 'percentage': 3.61, 'available_percentage': 3.85})
            self.assertEqual(sum(row['count'] for row in countries['rows']), 78)
            self.assertEqual(countries['unavailable_rows'], [unavailable])
            self.assertEqual(len(versions['rows']), 20)
            self.assertNotIn('page', versions)
            self.assertContains(page, '<aside')
            self.assertContains(page, 'Viewers without available information')
            full = self.client.get(url, {**params, 'show_all_countries': 1, 'show_all_versions': 1})
            all_countries, all_versions = full.context['sections']
            self.assertEqual(all_countries['page'].paginator.count, 12)
            self.assertEqual(all_versions['page'].paginator.count, 25)
            collapsed_query = parse_qs(urlsplit(all_countries['toggle_url']).query)
            self.assertNotIn('show_all_countries', collapsed_query)
            self.assertEqual(collapsed_query['show_all_versions'], ['1'])
            exported = self.client.get(url, {**params, 'export': 'csv'})
            rows = list(csv.DictReader(StringIO(exported.content.decode())))
            self.assertEqual(len(rows), 38)
            self.assertFalse(any(row['Metric'].startswith('Other countries') for row in rows))
            self.assertTrue(any(row['Metric'] == 'No approved credential application' for row in rows))

    def test_usage_overview_includes_approved_viewer_percentage_without_extra_column(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('usage_stats'), {'start_date': '2020-01-01', 'end_date': '2020-12-31'})
        overview = next(section for section in response.context['sections'] if section['title'] == 'Overview')
        approved = next(row for row in overview['rows']
                        if row['label'] == 'Viewers with an approved credential application')
        self.assertEqual(approved['count'], 1)
        self.assertEqual(approved['percentage'], 50.0)
        self.assertFalse(overview['show_percentage'])
        self.assertContains(response, '50.00% of all viewers')
