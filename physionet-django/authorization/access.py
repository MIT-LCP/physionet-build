import datetime

from django.db.models import Q

from events.models import Event, EventDataset
from project.models import AccessPolicy, DUASignature, DataAccessRequest
from user.models import Training, TrainingType


class Authorization:
    """Authorization class for authorization of user access to a Project and its resources."""

    def __init__(self, user):
        self.user = user

    def can_access_project(self, project):
        """Check if user can access project."""
        if project.deprecated_files:
            return False

        if not project.allow_file_downloads:
            return False

        if project.access_policy == AccessPolicy.OPEN:
            return True
        elif project.access_policy == AccessPolicy.RESTRICTED:
            return self.user.is_authenticated and DUASignature.objects.filter(project=project, user=self.user).exists()
        elif project.access_policy == AccessPolicy.CREDENTIALED:
            return (
                    self.user.is_authenticated
                    and self.user.is_credentialed
                    and DUASignature.objects.filter(project=project, user=self.user).exists()
                    and Training.objects.get_valid()
                    .filter(training_type__in=project.required_trainings.all(), user=self.user)
                    .count()
                    == project.required_trainings.count()
            )
        elif project.access_policy == AccessPolicy.CONTRIBUTOR_REVIEW:
            return (
                    self.user.is_authenticated
                    and self.user.is_credentialed
                    and DataAccessRequest.objects.get_active(
                        project=project,
                        requester=self.user,
                        status=DataAccessRequest.ACCEPT_REQUEST_VALUE
                    ).exists()
                    and Training.objects.get_valid()
                    .filter(training_type__in=project.required_trainings.all(), user=self.user)
                    .count()
                    == project.required_trainings.count()
            )
        return False

    def get_accessible_projects(self):
        """Return all projects user can access."""
        query = Q(access_policy=AccessPolicy.OPEN) & Q(deprecated_files=False)

        dua_signatures = DUASignature.objects.filter(user=self.user)

        if self.user.is_authenticated:
            query |= Q(access_policy=AccessPolicy.RESTRICTED) & Q(
                duasignature__in=dua_signatures
            )

        if self.user.is_credentialed:
            completed_training = (
                Training.objects.get_valid()
                .filter(user=self.user)
                .values_list("training_type")
            )
            not_completed_training = TrainingType.objects.exclude(
                pk__in=completed_training
            )
            required_training_complete = ~Q(
                required_trainings__in=not_completed_training
            )

            accepted_data_access_requests = DataAccessRequest.objects.filter(
                requester=self.user, status=DataAccessRequest.ACCEPT_REQUEST_VALUE
            )
            contributor_review_with_access = Q(
                access_policy=AccessPolicy.CONTRIBUTOR_REVIEW
            ) & Q(data_access_requests__in=accepted_data_access_requests)

            credentialed_with_dua_signed = Q(
                access_policy=AccessPolicy.CREDENTIALED
            ) & Q(duasignature__in=dua_signatures)

            query |= required_training_complete & (
                    contributor_review_with_access | credentialed_with_dua_signed
            )

        # add projects that are accessible through events
        events_all = Event.objects.filter(Q(host=self.user) | Q(participants__user=self.user))
        active_events = set(events_all.filter(end_date__gte=datetime.now()))
        accessible_datasets = EventDataset.objects.filter(event__in=active_events, is_active=True)
        accessible_projects_ids = []
        for event_dataset in accessible_datasets:
            if event_dataset.has_access(self.user):
                accessible_projects_ids.append(event_dataset.dataset.id)
        query |= Q(id__in=accessible_projects_ids)

        return self.filter(query).distinct()
