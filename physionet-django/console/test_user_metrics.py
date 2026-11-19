import csv
from datetime import date, timedelta
from io import StringIO

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from console.user_metrics import USER_DATES_CACHE_KEY, last_login_summary, user_trend
from user.models import User


class TestUserMetrics(TestCase):
    fixtures = ['demo-user.json']

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.get(email='admin@mit.edu')
        cls.admin.user_permissions.add(Permission.objects.get(codename='can_view_stats'))
        User.objects.update(join_date=date(2019, 6, 1))
        cls.existing = User.objects.count()
        for index, (joined, active, sso) in enumerate([
            (date(2020, 1, 5), True, False),
            (date(2020, 1, 31), False, False),
            (date(2020, 3, 1), True, True),
            (date(2020, 4, 1), True, False),
        ]):
            user = User.objects.create_user(f'joined-{index}@example.com', 'password', f'joined-{index}',
                                            is_active=active)
            User.objects.filter(pk=user.pk).update(join_date=joined, sso_id=f'sso-{index}' if sso else None)

    def setUp(self):
        cache.delete(USER_DATES_CACHE_KEY)

    def test_monthly_new_accounts_and_running_total(self):
        report, total_report = user_trend(date(2020, 1, 1), date(2020, 3, 31))
        self.assertEqual([row[:5] for row in report['rows']], [
            ['2020-01', 2, 1, 0, self.existing + 2],
            ['2020-02', 0, 0, 0, self.existing + 2],
            ['2020-03', 1, 1, 1, self.existing + 3],
        ])
        self.assertEqual(report['chart']['series'][0]['values'], [2, 0, 1])
        self.assertEqual(total_report['chart']['series'][0]['values'],
                         [self.existing + 2, self.existing + 2, self.existing + 3])

    def test_last_login_bands_cover_every_active_account(self):
        now = timezone.now()
        User.objects.update(last_login=None)
        User.objects.filter(email='joined-0@example.com').update(last_login=now - timedelta(days=3))
        User.objects.filter(email='joined-2@example.com').update(last_login=now + timedelta(minutes=5))
        User.objects.filter(email='joined-3@example.com').update(last_login=now - timedelta(days=400))
        summary = last_login_summary(now)
        counts = {row[0]: row[1] for row in summary['rows']}
        self.assertEqual(counts['Within 30 days'], 2)
        self.assertEqual(counts['365 days or more'], 1)
        self.assertEqual(summary['total'], User.objects.filter(is_active=True).count())

    def test_page_and_csv_exports(self):
        self.client.force_login(self.admin)
        url = reverse('user_stats')
        dates = {'start_date': '2020-01-01', 'end_date': '2020-03-31'}
        response = self.client.get(url, dates)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New user accounts by month')
        self.assertContains(response, 'Active accounts by last login')
        self.assertContains(response, 'data-chart-downloads-for="users-last-login"')
        rows = list(csv.reader(StringIO(self.client.get(url, {**dates, 'export': 'monthly'}).content.decode())))
        self.assertEqual(rows[1][:3], ['2020-01', '2', '1'])
        rows = list(csv.reader(StringIO(self.client.get(url, {**dates, 'export': 'total-monthly'}).content.decode())))
        self.assertEqual(rows[3][:2], ['2020-03', str(self.existing + 3)])
        rows = list(csv.reader(StringIO(self.client.get(url, {'export': 'last-login'}).content.decode())))
        self.assertEqual(rows[0], ['Snapshot', 'Last login', 'Accounts', 'Share (%)'])

    def test_invalid_dates_return_bad_request(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('user_stats'), {'start_date': '2020-03-01', 'end_date': '2020-01-01'})
        self.assertEqual(response.status_code, 400)

    def test_page_requires_stats_permission(self):
        self.client.force_login(User.objects.get(email='joined-0@example.com'))
        self.assertNotEqual(self.client.get(reverse('user_stats')).status_code, 200)
