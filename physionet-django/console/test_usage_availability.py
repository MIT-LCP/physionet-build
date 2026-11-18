from datetime import date, datetime, timezone as dt_timezone

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from console.metrics_test_utils import MetricsTestCase
from console.usage import UsageDateForm, usage_record_dates
from project.models import AccessLog, PublishedProject


class TestUsageAvailability(MetricsTestCase):
    def setUp(self):
        super().setUp()
        cache.delete('console:usage:record-dates:v1')
        self.addCleanup(cache.delete, 'console:usage:record-dates:v1')

    @override_settings(TIME_ZONE='America/New_York')
    def test_bounds_use_dataset_logs_and_local_dates_and_are_cached(self):
        AccessLog.objects.all().delete()
        with timezone.override('America/New_York'):
            self.create_log(self.dataset, self.viewer, datetime(2020, 1, 1, 4, 30, tzinfo=dt_timezone.utc),
                            datetime(2020, 2, 1, 5, 30, tzinfo=dt_timezone.utc))
            self.create_log(self.dataset, self.other, datetime(2020, 1, 15, 12, tzinfo=dt_timezone.utc))
            self.create_log(self.active, self.viewer, timezone.make_aware(datetime(2018, 1, 1)))
            software = PublishedProject.objects.filter(resource_type_id=1).first()
            self.create_log(software, self.viewer, timezone.make_aware(datetime(2017, 1, 1)))
            # The last bound is the latest session start, matching how the metrics select sessions.
            self.assertEqual(usage_record_dates(), {'first': date(2019, 12, 31), 'last': date(2020, 1, 15)})
            with self.assertNumQueries(0):
                self.assertEqual(usage_record_dates()['first'], date(2019, 12, 31))

    def test_empty_database_has_no_date_restriction(self):
        AccessLog.objects.all().delete()
        self.assertEqual(usage_record_dates(), {'first': None, 'last': None})
        form = UsageDateForm({'start_date': '2020-01-01', 'end_date': '2020-12-31'})
        self.assertTrue(form.is_valid())

    def test_form_allows_today_and_rejects_dates_before_first_record(self):
        first = date(2020, 6, 15)
        form = UsageDateForm({'start_date': first, 'end_date': timezone.localdate()}, first_record_date=first)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.fields['start_date'].widget.attrs['min'], '2020-06-15')
        self.assertEqual(form.fields['end_date'].widget.attrs['max'], timezone.localdate().isoformat())
        invalid = UsageDateForm({'start_date': '2020-06-14', 'end_date': '2020-06-15'}, first_record_date=first)
        self.assertFalse(invalid.is_valid())
        self.assertIn('start_date', invalid.errors)

    def test_page_and_exports_enforce_bounds(self):
        self.client.force_login(self.admin)
        url = reverse('usage_stats')
        for export in ('', 'csv', 'monthly'):
            response = self.client.get(url, {'start_date': '2020-01-01', 'end_date': '2020-12-31',
                                             'export': export})
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, 'Start date cannot be before the first available record', status_code=400)
        valid = self.client.get(url, {'start_date': '2020-06-15', 'end_date': '2020-12-31'})
        self.assertEqual(valid.status_code, 200)
        self.assertContains(valid, 'Available records:')
        self.assertContains(valid, 'min="2020-06-15"')
