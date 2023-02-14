from django.db.models import Manager, Q
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

        return self.filter(query)
