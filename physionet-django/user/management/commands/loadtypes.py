"""
Command to:
- reset and load fixtures for project structures
"""
import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from user.models import Training, TrainingType, TrainingQuestion, CredentialApplication
from user.enums import TrainingStatus


class Command(BaseCommand):

    def _fixture_path(self, app_name, fixture_file_name):
        return os.path.join(settings.BASE_DIR, app_name, 'fixtures', fixture_file_name)

    def handle(self, *args, **options):
        # Load project types
        call_command('loaddata', self._fixture_path('project', 'project-types.json'), verbosity=1)

        call_command('loaddata', self._fixture_path('user', 'demo-training-type.json'))

        training_type = TrainingType.objects.first()

        status_mapping = {
            0: TrainingStatus.REVIEW,
            1: TrainingStatus.REJECTED,
            2: TrainingStatus.ACCEPTED,
            3: TrainingStatus.WITHDRAWN,
            4: TrainingStatus.REJECTED
        }

        for credential_application in CredentialApplication.objects.all():
            report_url = (
                ""
                if credential_application.training_completion_report_url is None
                else credential_application.training_completion_report_url
            )

            training = Training.objects.create(
                slug=credential_application.slug,
                training_type=training_type,
                user=credential_application.user,
                completion_report=credential_application.training_completion_report,
                completion_report_url=report_url,
                application_datetime=credential_application.training_completion_date,
                process_datetime=credential_application.decision_datetime,
                status=status_mapping[credential_application.status],
            )

            training_questions = []
            for question in training.training_type.questions.all():
                training_questions.append(TrainingQuestion(training=training, question=question))

            TrainingQuestion.objects.bulk_create(training_questions)
