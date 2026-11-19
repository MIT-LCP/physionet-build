import csv
from datetime import date, datetime, timedelta
from io import StringIO

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from console.training_metrics import (
    TRAINING_DATES_CACHE_KEY, approval_trend, expiry_summary, review_queue, review_time_trend, submission_trend,
    type_summary,
)
from training.models import Course
from user.enums import RequiredField, TrainingStatus
from user.models import CITIVerification, Training, TrainingType, User


def when(month, day, hour=12):
    return timezone.make_aware(datetime(2020, month, day, hour))


class TestTrainingMetrics(TestCase):
    fixtures = ['demo-user.json']

    @classmethod
    def setUpTestData(cls):
        Training.objects.all().delete()
        cls.admin = User.objects.get(email='admin@mit.edu')
        cls.admin.user_permissions.add(Permission.objects.get(codename='can_view_stats'))
        cls.citi = TrainingType.objects.create(name='CITI Metrics', valid_duration=timedelta(days=365),
                                               required_field=RequiredField.DOCUMENT)
        cls.other_type = TrainingType.objects.create(name='Other Metrics', required_field=RequiredField.URL)
        cls.platform = TrainingType.objects.create(name='Platform Metrics', required_field=RequiredField.PLATFORM)
        cls.course = Course.objects.create(training_type=cls.platform, version='1.0',
                                           valid_duration=timedelta(days=100))
        cls.users = [User.objects.create_user(f'trainee-{i}@example.com', 'password', f'trainee-{i}', is_active=True)
                     for i in range(5)]

    def setUp(self):
        cache.delete(TRAINING_DATES_CACHE_KEY)

    def create(self, user, status, submitted, processed=None, training_type=None, auto=False, course=None):
        training = Training.objects.create(slug=f'metrics-{Training.objects.count()}', user=user, status=status,
                                           training_type=training_type or self.citi, course=course)
        Training.objects.filter(pk=training.pk).update(application_datetime=submitted, process_datetime=processed)
        if auto:
            CITIVerification.objects.create(training=training, auto_approved=True)
        return training

    def test_submissions_by_month_and_current_outcome(self):
        self.create(self.users[0], TrainingStatus.ACCEPTED, when(1, 5), when(1, 7))
        self.create(self.users[1], TrainingStatus.REJECTED, when(1, 6), when(2, 1))
        self.create(self.users[2], TrainingStatus.WITHDRAWN, when(3, 1))
        self.create(self.users[3], TrainingStatus.REVIEW, when(3, 2))
        self.create(self.users[4], TrainingStatus.IN_PROGRESS, when(3, 3), when(3, 3), self.platform)
        report = submission_trend(date(2020, 1, 1), date(2020, 3, 31))
        self.assertEqual([row[:6] for row in report['rows']], [
            ['2020-01', 2, 1, 1, 0, 0], ['2020-02', 0, 0, 0, 0, 0], ['2020-03', 2, 0, 0, 1, 1],
        ])
        self.assertEqual(report['chart']['type'], 'stacked-bar')

    def test_acceptances_by_approval_path(self):
        self.create(self.users[0], TrainingStatus.ACCEPTED, when(1, 1), when(1, 1), auto=True)
        self.create(self.users[1], TrainingStatus.ACCEPTED, when(1, 1), when(1, 9))
        self.create(self.users[2], TrainingStatus.ACCEPTED, when(1, 2), when(1, 2), self.platform, course=self.course)
        self.create(self.users[3], TrainingStatus.REJECTED, when(1, 2), when(1, 3))
        report = approval_trend(date(2020, 1, 1), date(2020, 1, 31))
        self.assertEqual(report['rows'][0][:5], ['2020-01', 3, 1, 1, 1])

    def test_review_time_uses_manual_decisions_only(self):
        self.create(self.users[0], TrainingStatus.ACCEPTED, when(1, 1), when(1, 3))
        self.create(self.users[1], TrainingStatus.REJECTED, when(1, 1), when(1, 11))
        self.create(self.users[2], TrainingStatus.ACCEPTED, when(1, 1), when(1, 1), auto=True)
        self.create(self.users[3], TrainingStatus.ACCEPTED, when(1, 2), when(1, 2), self.platform, course=self.course)
        report = review_time_trend(date(2020, 1, 1), date(2020, 1, 31))
        self.assertEqual(report['rows'][0][:4], ['2020-01', 6.0, 9.2, 2])

    def test_type_summary_acceptance_rate(self):
        self.create(self.users[0], TrainingStatus.ACCEPTED, when(1, 1), when(1, 2))
        self.create(self.users[1], TrainingStatus.REJECTED, when(1, 1), when(1, 2))
        self.create(self.users[2], TrainingStatus.WITHDRAWN, when(1, 1))
        self.create(self.users[3], TrainingStatus.REVIEW, when(1, 1), training_type=self.other_type)
        summary = type_summary(date(2020, 1, 1), date(2020, 1, 31))
        self.assertEqual(summary['rows'], [['CITI Metrics', 3, 1, 1, 1, 0, 50.0],
                                           ['Other Metrics', 1, 0, 0, 0, 1, None]])

    def test_review_queue_age_bands(self):
        now = timezone.now()
        for user, days in zip(self.users, (1, 10, 40, 200)):
            self.create(user, TrainingStatus.REVIEW, now - timedelta(days=days))
        self.create(self.users[4], TrainingStatus.ACCEPTED, now - timedelta(days=3), now)
        queue = review_queue(now)
        self.assertEqual([row[1] for row in queue['rows']], [1, 1, 1, 1])
        self.assertIn('4 trainings awaiting review', queue['summary'])

    def test_expiry_uses_latest_training_per_person_and_type(self):
        now = timezone.now()
        self.create(self.users[0], TrainingStatus.ACCEPTED, now, now - timedelta(days=400))
        self.create(self.users[0], TrainingStatus.ACCEPTED, now, now - timedelta(days=350))
        self.create(self.users[1], TrainingStatus.ACCEPTED, now, now - timedelta(days=370))
        self.create(self.users[2], TrainingStatus.ACCEPTED, now, now, self.other_type)
        self.create(self.users[3], TrainingStatus.ACCEPTED, now, now - timedelta(days=50), self.platform,
                    course=self.course)
        summary = expiry_summary(now)
        totals = dict(zip(summary['chart']['labels'], summary['chart']['series'][0]['values']))
        self.assertEqual(totals['Expired'], 1)
        self.assertEqual(totals['Expires within 30 days'], 1)
        self.assertEqual(totals['Expires in 30–59 days'], 1)
        self.assertEqual(totals['Does not expire'], 1)

    def test_page_and_csv_exports(self):
        self.create(self.users[0], TrainingStatus.ACCEPTED, when(1, 5), when(1, 7))
        self.client.force_login(self.admin)
        url = reverse('training_stats')
        # The start date cannot precede the first submission on record.
        dates = {'start_date': '2020-01-05', 'end_date': '2020-01-31'}
        response = self.client.get(url, dates)
        self.assertEqual(response.status_code, 200)
        for title in ('Training submissions by month and current outcome', 'Accepted trainings by month',
                      'Time to review by month', 'Submissions by training type', 'Trainings awaiting review',
                      'Upcoming training expirations'):
            self.assertContains(response, title)
        for export, first in (('monthly', '2020-01'), ('approvals', '2020-01'), ('review-time', '2020-01'),
                              ('types', 'CITI Metrics')):
            rows = list(csv.reader(StringIO(self.client.get(url, {**dates, 'export': export}).content.decode())))
            self.assertEqual(rows[1][0], first)
        for export in ('queue', 'expiry'):
            rows = list(csv.reader(StringIO(self.client.get(url, {'export': export}).content.decode())))
            self.assertEqual(rows[0][0], 'Snapshot')

    def test_page_requires_stats_permission(self):
        self.client.force_login(self.users[0])
        self.assertNotEqual(self.client.get(reverse('training_stats')).status_code, 200)
