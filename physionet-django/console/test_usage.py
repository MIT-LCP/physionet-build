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

from console.usage import usage_metrics
from project.models import AccessLog, ActiveProject, Author, DataAccessRequest, PublishedAuthor, PublishedProject
from user.models import CredentialApplication, User


class TestUsageMetrics(TestCase):
    fixtures = ['demo-training-type.json', 'demo-user.json', 'site-data.json', 'demo-project.json']

    @classmethod
    def setUpTestData(cls):
        AccessLog.objects.all().delete()
        DataAccessRequest.objects.all().delete()
        ActiveProject.objects.update(submission_datetime=None)
        PublishedProject.objects.update(submission_datetime=None)
        cls.when = timezone.make_aware(datetime(2020, 6, 15, 12))
        cls.dataset = PublishedProject.objects.filter(resource_type_id=0).first()
        PublishedProject.objects.filter(pk=cls.dataset.pk).update(submission_datetime=cls.when)
        cls.dataset.refresh_from_db()
        cls.version = copy.copy(cls.dataset)
        cls.version.pk = None
        cls.version.version = 'usage-test'
        cls.version.submission_slug = 'usage-test'
        cls.version.public_project_uuid = uuid4()
        cls.version.is_latest_version = False
        cls.version.featured = None
        cls.version.save()
        cls.active = ActiveProject.objects.first()
        ActiveProject.objects.filter(pk=cls.active.pk).update(submission_datetime=cls.when)
        cls.active.refresh_from_db()

        cls.viewer = User.objects.create_user('usage-one@example.com', 'password', 'usage-one', is_active=True)
        cls.other = User.objects.create_user('usage-two@example.com', 'password', 'usage-two', is_active=True)
        cls.coauthor = User.objects.create_user('usage-three@example.com', 'password', 'usage-three', is_active=True)
        cls.admin = User.objects.get(email='admin@mit.edu')
        cls.admin.user_permissions.add(Permission.objects.get(codename='can_view_stats'))

        for index, (country, category, status) in enumerate([
            ('BR', 2, CredentialApplication.Status.ACCEPTED),
            ('US', 4, CredentialApplication.Status.ACCEPTED),
            ('GB', 0, CredentialApplication.Status.REJECTED),
        ]):
            application = CredentialApplication.objects.create(
                user=cls.viewer, slug=f'usage-credential-{index}', country=country,
                researcher_category=category, status=status,
                course_category=1 if index == 1 else None,
            )
            CredentialApplication.objects.filter(pk=application.pk).update(
                application_datetime=cls.when + timezone.timedelta(days=index),
            )

        for project in (cls.dataset, cls.version):
            project.authors.all().delete()
            PublishedAuthor.objects.create(project=project, user=cls.viewer, display_order=1, is_submitting=True)
        PublishedAuthor.objects.create(project=cls.dataset, user=cls.coauthor, display_order=2)
        cls.active.authors.all().delete()
        Author.objects.create(project=cls.active, user=cls.other, display_order=1, is_submitting=True)

        for project, user in (
            (cls.dataset, cls.viewer), (cls.dataset, cls.viewer),
            (cls.version, cls.viewer), (cls.version, cls.other),
        ):
            cls.create_log(project, user, cls.when)

    @classmethod
    def create_log(cls, project, user, when, last_access=None):
        log = AccessLog.objects.create(project=project, user=user, count=10)
        AccessLog.objects.filter(pk=log.pk).update(creation_datetime=when, last_access_datetime=last_access or when)
        return log

    def metrics(self, start=date(2020, 1, 1), end=date(2020, 12, 31)):
        return {section['title']: section['rows'] for section in usage_metrics(start, end)}

    def overview(self, metrics):
        return {row['label']: row['count'] for row in metrics['Overview']}

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
        self.assertEqual(countries['Not available']['percentage'], 50)
        categories = {row['label']: row['count'] for row in metrics['Dataset viewers by researcher category']}
        self.assertEqual(categories, {'Industry Researcher': 1, 'Not available': 1})
        self.assertEqual(self.overview(metrics)['Viewers with an approved credential application'], 1)

    def test_course_use_is_declared_in_latest_approved_credential(self):
        rows = {row['label']: row['count'] for row in self.metrics()['Declared course use']}
        self.assertEqual(rows, {'I am taking a course using the data': 1, 'Not available': 1})

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

    def create_request(self, user, project=None, status=DataAccessRequest.ACCEPT_REQUEST_VALUE,
                       requested=None, decided=None):
        request = DataAccessRequest.objects.create(
            requester=user, project=project or self.dataset, status=status,
            decision_datetime=decided or self.when,
        )
        DataAccessRequest.objects.filter(pk=request.pk).update(request_datetime=requested or self.when)
        return request

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
        self.assertEqual(countries, {'United States of America': 1, 'Not available': 1})

    def test_request_and_approval_date_boundaries(self):
        start = timezone.make_aware(datetime(2020, 1, 1))
        end = timezone.make_aware(datetime(2021, 1, 1))
        self.create_request(self.viewer, requested=start, decided=start)
        self.create_request(self.other, requested=end, decided=end)
        overview = self.overview(self.metrics())
        self.assertEqual(overview['Dataset access requests submitted'], 1)
        self.assertEqual(overview['Unique users approved for dataset access during selected dates'], 1)

    def test_version_viewers_are_deduplicated_within_each_version(self):
        rows = {row['label']: row['count'] for row in self.metrics()['Registered viewers by dataset version']}
        self.assertEqual(rows, {
            f'{self.dataset.slug} / {self.dataset.version}': 1,
            f'{self.version.slug} / {self.version.version}': 2,
        })

    def test_institution_names_are_normalized_without_guessing_aliases(self):
        CredentialApplication.objects.filter(user=self.viewer).update(organization_name='  Example   University ')
        CredentialApplication.objects.create(
            user=self.other, slug='usage-other-credential', country='BR', researcher_category=0,
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
        for title in ('Dataset viewers by account age', 'Submitting authors by account age',
                      'Approved dataset users by account age'):
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
            for section in page.context['sections'] for row in section['rows']
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
        self.assertEqual(report['rows'], [['2020-06', 3, 1, 1, 'Partial month'], ['2020-07', 0, 1, 0, 'Full month'], ['2020-08', 0, 0, 0, 'Partial month']])
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
        self.assertContains(response, 'not filtered by the historical dates')
        export = self.client.get(url, {'export': 'pending'})
        rows = list(csv.DictReader(StringIO(export.content.decode())))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Elapsed days'], str(row['days']))

    def credential(self, status, submitted=None, decided=None, **fields):
        app = CredentialApplication.objects.create(
            user=self.viewer, slug=f'operational-{uuid4().hex[:8]}', researcher_category=0,
            status=status, decision_datetime=decided, **fields,
        )
        CredentialApplication.objects.filter(pk=app.pk).update(application_datetime=submitted or self.when)
        return app

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
        self.assertEqual(report['rows'], [['2020-06', 2.25, 2, 4.0, 1, 'Full month'], ['2020-07', None, 0, None, 0, 'Full month']])
        self.assertEqual(report['volume']['chart'], {
            'type': 'stacked-bar', 'labels': ['2020-06', '2020-07'], 'partial': [False, False],
            'series': [{'name': 'Accepted decisions', 'values': [2, 0]},
                       {'name': 'Rejected decisions', 'values': [1, 0]}],
        })
        self.assertIn('Excluded negative durations: 1', report['description'])
        self.client.force_login(self.admin)
        params = {'start_date': '2020-06-01', 'end_date': '2020-07-31'}
        page = self.client.get(reverse('credentialing_stats'), params)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['report'], report)
        self.assertContains(page, 'Credentialing decision volume by month')
        self.assertContains(page, 'data-metrics-chart="credentialing-volume"')
        export = self.client.get(reverse('credentialing_stats'), {**params, 'export': 'monthly'})
        self.assertEqual(list(csv.reader(StringIO(export.content.decode())))[-1], ['2020-07', '', '0', '', '0', 'Full month'])

    def test_credential_queue_and_repeated_applications_are_descriptive(self):
        from console.reporting import pending_credentials, credential_queue_rows, repeated_credentials
        CredentialApplication.objects.all().delete()
        pending = CredentialApplication.Status.PENDING
        self.credential(pending)
        self.credential(pending, reference_contact_datetime=self.when)
        self.credential(pending, reference_contact_datetime=self.when, reference_response_datetime=self.when)
        self.credential(CredentialApplication.Status.WITHDRAWN)
        rows = credential_queue_rows(pending_credentials(timezone.now()), timezone.now())
        self.assertEqual([r['status'] for r in rows], ['Awaiting reference contact', 'Awaiting reference response',
                                                     'Awaiting processing after reference response'])
        users = list(repeated_credentials(date(2020, 1, 1), date(2020, 12, 31)))
        self.assertEqual(len(users), 1)
        self.assertEqual((users[0]['total'], users[0]['pending'], users[0]['withdrawn']), (4, 3, 1))
        self.client.force_login(self.admin)
        response = self.client.get(reverse('credentialing_stats'), {'export': 'pending'})
        self.assertEqual(len(list(csv.DictReader(StringIO(response.content.decode())))), 3)

    def test_operational_exports_require_permission_and_valid_historical_dates(self):
        for view in ('credentialing_stats', 'editorial_stats'):
            for export in ('monthly', 'pending', 'repeated'):
                self.assertEqual(self.client.get(reverse(view), {'export': export}).status_code, 403)
            self.client.force_login(self.admin)
            response = self.client.get(reverse(view), {'start_date': 'bad', 'export': 'monthly'})
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('Content-Disposition', response)
            self.client.logout()

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
        self.assertContains(response, 'NOT time in the current stage')
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

    def test_submission_contributors_are_separate_from_dataset_usage(self):
        self.client.force_login(self.admin)
        dates = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
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

    def test_access_queue_paginates_but_exports_all_pending_requests(self):
        DataAccessRequest.objects.bulk_create([
            DataAccessRequest(requester=self.viewer, project=self.dataset, status=DataAccessRequest.PENDING_VALUE)
            for _ in range(51)
        ])
        self.client.force_login(self.admin)
        url = reverse('access_request_stats')
        first = self.client.get(url)
        self.assertEqual(len(first.context['queue_rows']), 50)
        self.assertEqual(first.context['queue_total'], 51)
        second = self.client.get(url, {'page': 2})
        self.assertEqual(len(second.context['queue_rows']), 1)
        export = self.client.get(url, {'export': 'pending'})
        self.assertEqual(len(list(csv.DictReader(StringIO(export.content.decode())))), 51)

    def test_repeated_credentials_paginate_five_users_and_export_everyone(self):
        CredentialApplication.objects.all().delete()
        for index in range(6):
            user = User.objects.create_user(email=f'repeated-{index}@example.invalid', password=None,
                                            username=f'repeated-{index}')
            for attempt in range(2):
                app = CredentialApplication.objects.create(
                    user=user, slug=f'repeated-{index}-{attempt}', researcher_category=0,
                    status=CredentialApplication.Status.PENDING,
                )
                CredentialApplication.objects.filter(pk=app.pk).update(application_datetime=self.when)
        self.client.force_login(self.admin)
        url = reverse('credentialing_stats')
        params = {'start_date': '2020-01-01', 'end_date': '2020-12-31'}
        first = self.client.get(url, params)
        self.assertEqual(first.context['repeated_total'], 6)
        self.assertEqual(len(first.context['repeated']['rows']), 5)
        self.assertContains(first, 'repeated_page=2#repeated-applications')
        second = self.client.get(url, {**params, 'repeated_page': 2})
        self.assertEqual(len(second.context['repeated']['rows']), 1)
        self.assertTrue(set(row[0] for row in first.context['repeated']['rows']).isdisjoint(
            row[0] for row in second.context['repeated']['rows']))
        export = self.client.get(url, {**params, 'export': 'repeated', 'repeated_page': 2})
        self.assertEqual(len(list(csv.DictReader(StringIO(export.content.decode())))), 6)

    def test_credential_volume_empty_months_are_zero(self):
        from console.reporting import credential_trend
        report = credential_trend(date(2010, 1, 1), date(2010, 2, 28))
        self.assertEqual(report['volume']['chart']['labels'], ['2010-01', '2010-02'])
        for series in report['volume']['chart']['series']:
            self.assertEqual(series['values'], [0, 0])
