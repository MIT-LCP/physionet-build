from django.db.models import DateTimeField, ExpressionWrapper, QuerySet, F, Q
from django.utils import timezone

from user.enums import TrainingStatus


class TrainingQuerySet(QuerySet):
    def get_review(self):
        return self.filter(status=TrainingStatus.REVIEW)

    def get_valid(self):
        return self.filter(
            Q(status=TrainingStatus.ACCEPTED),
            Q(training_type__valid_duration__isnull=True)
            | Q(process_datetime__gte=timezone.now() - F('training_type__valid_duration')),
        ).annotate(
            valid_datetime=ExpressionWrapper(
                F('process_datetime') + F('training_type__valid_duration'), output_field=DateTimeField()
            )
        )

    def get_expired(self):
        return self.filter(
            status=TrainingStatus.ACCEPTED, process_datetime__lt=timezone.now() - F('training_type__valid_duration')
        ).annotate(
            valid_datetime=ExpressionWrapper(
                F('process_datetime') + F('training_type__valid_duration'), output_field=DateTimeField()
            )
        )

    def get_rejected(self):
        return self.filter(status=TrainingStatus.REJECTED)
