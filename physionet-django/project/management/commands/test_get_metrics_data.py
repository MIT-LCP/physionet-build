import os

from django.core.management import call_command
from django.test import TestCase

from project.management.commands import get_metrics_data
from project.models import PublishedProject, Metrics

from project.management.commands.get_metrics_data import InvalidLogError


class TestGetMetricsData(TestCase):

    def get_projects(self):
        demoeicu = PublishedProject.objects.get(slug='demoeicu',
                                                is_latest_version=True).core_project
        demoecg = PublishedProject.objects.get(slug='demoecg',
                                               is_latest_version=True).core_project
        demobsn = PublishedProject.objects.get(slug='demobsn',
                                               is_latest_version=True).core_project
        demoselfmanaged = PublishedProject.objects.get(slug='demoselfmanaged',
                                                       is_latest_version=True).core_project
        demopsn = PublishedProject.objects.get(slug='demopsn',
                                               is_latest_version=True).core_project
        return demoeicu, demoecg, demobsn, demoselfmanaged, demopsn

    def test_update_metrics(self):
        """
        Test if view counts get updated in database.
        """
        path = os.path.join('project', 'fixtures', 'physionet_access.log.3')
        call_command('get_metrics_data', str(path))
        demoeicu, demoecg, demobsn, demoselfmanaged, demopsn = self.get_projects()
        self.assertEqual(Metrics.objects.filter(
            core_project=demoeicu).latest('date').running_viewcount, 20)
        self.assertEqual(Metrics.objects.filter(
            core_project=demoecg).latest('date').running_viewcount, 20)
        self.assertEqual(Metrics.objects.filter(
            core_project=demobsn).latest('date').running_viewcount, 22)
        self.assertEqual(Metrics.objects.filter(
            core_project=demoselfmanaged).latest('date').running_viewcount, 18)
        self.assertEqual(Metrics.objects.filter(
            core_project=demopsn).latest('date').running_viewcount, 19)

    def test_multiple_logs(self):
        """
        Test if multiple logs can be parsed in one function call, in
        increasing date order.
        """
        path_1 = os.path.join('project', 'fixtures', 'physionet_access.log.1')
        path_2 = os.path.join('project', 'fixtures', 'physionet_access.log.2')
        call_command('get_metrics_data', str(path_2), str(path_1))
        demoeicu, demoecg, demobsn, demoselfmanaged, demopsn = self.get_projects()
        self.assertEqual(Metrics.objects.filter(
            core_project=demoeicu).latest('date').running_viewcount, 43)
        self.assertEqual(Metrics.objects.filter(
            core_project=demoecg).latest('date').running_viewcount, 43)
        self.assertEqual(Metrics.objects.filter(
            core_project=demobsn).latest('date').running_viewcount, 32)
        self.assertEqual(Metrics.objects.filter(
            core_project=demoselfmanaged).latest('date').running_viewcount, 38)
        self.assertEqual(Metrics.objects.filter(
            core_project=demopsn).latest('date').running_viewcount, 41)

    def test_repeated_log(self):
        """
        Test if a warning is raised and view counts remain the same when the
            command is called on a previously parsed log file.
        """
        path_1 = os.path.join('project', 'fixtures', 'physionet_access.log.1')
        with self.assertWarns(UserWarning):
            call_command('get_metrics_data', str(path_1))
            call_command('get_metrics_data', str(path_1))
        call_command('get_metrics_data', str(path_1), str(path_2))
        demoeicu, demoecg, demobsn, demoselfmanaged, demopsn = self.get_projects()
        self.assertEqual(Metrics.objects.filter(
            core_project=demoeicu).latest('date').running_viewcount, 21)
        self.assertEqual(Metrics.objects.filter(
            core_project=demoecg).latest('date').running_viewcount, 16)
        self.assertEqual(Metrics.objects.filter(
            core_project=demobsn).latest('date').running_viewcount, 16)
        self.assertEqual(Metrics.objects.filter(
            core_project=demoselfmanaged).latest('date').running_viewcount, 24)
        self.assertEqual(Metrics.objects.filter(
            core_project=demopsn).latest('date').running_viewcount, 20)

    def test_invalid_log(self):
        """
        Test if InvalidLogError is raised when get_metrics_data is called
        on a non-log file.
        """
        path = os.path.join('project', 'fixtures', 'challenge.json')
        with self.assertRaises(InvalidLogError):
            call_command('get_metrics_data', str(path))
