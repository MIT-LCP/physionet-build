from datetime import datetime

from django.db.models import Manager, Q
from events.models import Event, EventDataset
from project.models import AccessPolicy, DUASignature, DataAccessRequest
from user.models import Training, TrainingType


class PublishedProjectManager(Manager):
    def accessible_by(self, user):
        """
        Return all published projects accessible by a specified user
        Part of the `hdn-research-environment` app contract
        The logic should mirror PublishedProject#has_access,
        but for all the projects in the database.
        """
        query = Q(access_policy=AccessPolicy.OPEN) & Q(deprecated_files=False)

        dua_signatures = DUASignature.objects.filter(user=user)

        if user.is_authenticated:
            query |= Q(access_policy=AccessPolicy.RESTRICTED) & Q(
                duasignature__in=dua_signatures
            )

        if user.is_credentialed:
            completed_training = (
                Training.objects.get_valid()
                .filter(user=user)
                .values_list("training_type")
            )
            not_completed_training = TrainingType.objects.exclude(
                pk__in=completed_training
            )
            required_training_complete = ~Q(
                required_trainings__in=not_completed_training
            )

            accepted_data_access_requests = DataAccessRequest.objects.filter(
                requester=user, status=DataAccessRequest.ACCEPT_REQUEST_VALUE
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

        # Event related logic
        # get all projects that are accessible by user through Events(Used by `hdn-research-environment` package)
        # get all active events that user is a participant/host of
        events_all = Event.objects.filter(Q(host=user) | Q(participants__user=user))
        active_events = set(events_all.filter(end_date__gte=datetime.now()))
        # get all accessible datasets for the events
        accessible_datasets = EventDataset.objects.filter(event__in=active_events, is_active=True)
        # get all projects that are accessible to the user
        accessible_projects_ids = []
        for event_dataset in accessible_datasets:
            if event_dataset.has_access(user):
                accessible_projects_ids.append(event_dataset.dataset.id)

        query |= Q(id__in=accessible_projects_ids)
        return self.filter(query)
