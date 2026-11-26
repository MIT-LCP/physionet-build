from datetime import datetime
from unittest import mock

from django.core import mail
from django.test import SimpleTestCase, override_settings

from notification.utility import task_failed_notify, task_rescheduled_notify

TASK_ARGS = ('Example task', 3, 'Traceback: example error', datetime(2026, 11, 1, 12, 0),
             'example.tasks.example_task', '[[1], {}]')


class TestTaskAlerts(SimpleTestCase):
    def test_alerts_are_sent_to_admins(self):
        task_failed_notify(*TASK_ARGS)
        task_rescheduled_notify(*TASK_ARGS)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('Example task has failed', mail.outbox[0].subject)
        self.assertIn('Example task has been rescheduled', mail.outbox[1].subject)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend')
    @mock.patch('smtplib.SMTP', side_effect=ConnectionRefusedError)
    def test_send_errors_are_logged_not_raised(self, _smtp):
        for notify, subject in ((task_failed_notify, 'Example task has failed'),
                                (task_rescheduled_notify, 'Example task has been rescheduled')):
            with self.subTest(notify=notify.__name__):
                with self.assertLogs('notification.utility', level='ERROR') as logs:
                    notify(*TASK_ARGS)
                self.assertIn(f'Could not send task alert email: {subject}', logs.output[0])
                self.assertIn('ConnectionRefusedError', logs.output[0])
