import csv
import io
from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from console.views import download_projects_view_counts
from physionet.enums import LogCategory
from project.models import AccessLog, CoreProject, Log, ProjectType, PublishedProject
from user.models import User


class TestProjectViewCountsExport(TestCase):
    def test_distinct_viewers_and_constant_query_count(self):
        resource_type, _ = ProjectType.objects.get_or_create(
            id=0, defaults={'name': 'Database', 'description': ''},
        )
        core = CoreProject.objects.create(doi='10.1234/example')
        old = PublishedProject.objects.create(
            title='Example', slug='example', submission_slug='example-old', version='1.0', core_project=core,
            resource_type=resource_type, is_latest_version=False,
        )
        latest = PublishedProject.objects.create(
            title='Example', slug='example', submission_slug='example-new', version='2.0', core_project=core,
            resource_type=resource_type, is_latest_version=True,
        )
        PublishedProject.objects.create(
            title='Empty', slug='empty', submission_slug='empty', version='1.0',
            core_project=CoreProject.objects.create(),
            resource_type=resource_type, is_latest_version=True,
        )
        user = User.objects.create(username='viewer-one', email='one@example.org')
        other_user = User.objects.create(username='viewer-two', email='two@example.org')
        view_logs = [
            AccessLog.objects.create(project=project, user=viewer)
            for project, viewer in ((old, user), (latest, user), (latest, user), (old, other_user))
        ]
        # Other log categories and content types must not count as project views.
        Log.objects.create(project=latest, user=other_user, category=LogCategory.GCP)
        Log.objects.create(
            content_type=ContentType.objects.get_for_model(CoreProject),
            object_id=latest.pk, user=other_user, category=LogCategory.ACCESS,
        )
        with mock.patch.object(PublishedProject, 'view_count', side_effect=AssertionError('N+1 query')):
            with self.assertNumQueries(3):
                response = download_projects_view_counts.__wrapped__(None)
        rows = {row['project_slug']: row for row in csv.DictReader(io.StringIO(response.content.decode()))}
        self.assertTrue({'example', 'empty'}.issubset(rows))
        self.assertEqual(rows['example']['count_current_version'], '1')
        self.assertEqual(rows['example']['count_all_versions'], '2')
        self.assertEqual(int(rows['example']['count_current_version']), latest.view_count())
        distinct_viewers = len({log.user_id for log in view_logs})
        all_version_count = int(rows['example']['count_all_versions'])
        self.assertEqual(all_version_count, distinct_viewers)
        # The shared viewer must count once across versions, unlike the old sum.
        old_sum = sum(version.view_count() for version in (old, latest))
        self.assertLess(all_version_count, old_sum)
        self.assertEqual(rows['example']['current_version'], '2.0')
        self.assertEqual(rows['example']['DOI (latest version)'], 'https://doi.org/10.1234/example')
        self.assertEqual(rows['empty']['count_current_version'], '0')
        self.assertEqual(rows['empty']['count_all_versions'], '0')
        # Adding another project must not increase the number of export queries.
        PublishedProject.objects.create(
            title='Another', slug='another', submission_slug='another', version='1.0',
            core_project=CoreProject.objects.create(),
            resource_type=resource_type, is_latest_version=True,
        )
        with self.assertNumQueries(3):
            download_projects_view_counts.__wrapped__(None)
