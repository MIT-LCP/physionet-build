from django.db.models import QuerySet, F, Q, Manager, ExpressionWrapper, DateTimeField
from django.db.models.functions import Coalesce
from django.utils import timezone


class DataAccessRequestQuerySet(QuerySet):
    def get_active(self, **kwargs):
        return self.filter(
            Q(status=self.model.ACCEPT_REQUEST_VALUE),
            Q(duration__isnull=True) | Q(decision_datetime__gte=timezone.now() - F('duration')),
            **kwargs
        )


class DataAccessRequestManager(Manager):
    def get_queryset(self):
        return super().get_queryset().annotate(
            valid_until=ExpressionWrapper(
                F('decision_datetime') + F('duration'),
                output_field=DateTimeField()
            )
        )
