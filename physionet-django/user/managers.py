from django.db.models import (DateTimeField, ExpressionWrapper, QuerySet, F, Q,
                              OuterRef, Subquery, Case, When)
from django.utils import timezone

from user.enums import TrainingStatus, RequiredField
from training.models import Course

class TrainingQuerySet(QuerySet):
    def get_review(self):
        """
        Get the document-based or URL-based training objects for the user, that are in the status REVIEW.
        """
        return self.filter(
            Q(status=TrainingStatus.REVIEW),
            Q(training_type__required_field=RequiredField.DOCUMENT)
            | Q(training_type__required_field=RequiredField.URL)
        )

    def in_progress(self):
        """
        Get the on-platform training objects for the user, that are in the status REVIEW.
        """
        return self.filter(
            Q(status=TrainingStatus.REVIEW),
            Q(training_type__required_field=RequiredField.PLATFORM)
        )

    def get_valid(self):
        """
        Get all the training objects that are in the status ACCEPTED and have not expired.
        """
        return self.filter(
            Q(status=TrainingStatus.ACCEPTED),
            Q(training_type__valid_duration__isnull=True)
            | Q(process_datetime__gte=timezone.now() - Case(
                When(training_type__required_field=RequiredField.PLATFORM, then=F('course__valid_duration')),
                default=F('training_type__valid_duration')
            )),
        ).annotate(
            valid_datetime=ExpressionWrapper(
                F('process_datetime') + Case(
                    When(training_type__required_field=RequiredField.PLATFORM, then=F('course__valid_duration')),
                    default=F('training_type__valid_duration')
                ), output_field=DateTimeField()
            )
        )

    def get_expired(self):
        """
        Get all the training objects that are in the status ACCEPTED and have expired
        """
        return self.filter(
            Q(status=TrainingStatus.ACCEPTED),
            Q(process_datetime__lt=timezone.now() - Case(
                When(training_type__required_field=RequiredField.PLATFORM, then=F('course__valid_duration')),
                default=F('training_type__valid_duration')
            )),
        ).annotate(
            valid_datetime=ExpressionWrapper(
                F('process_datetime') + Case(
                    When(training_type__required_field=RequiredField.PLATFORM, then=F('course__valid_duration')),
                    default=F('training_type__valid_duration')
                ), output_field=DateTimeField()
            )
        )

    def get_rejected(self):
        """
        Get all the training objects that are in the status REJECTED.
        """
        return self.filter(status=TrainingStatus.REJECTED)
