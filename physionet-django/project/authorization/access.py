from datetime import datetime

from django.db.models import Q

from events.models import Event, EventDataset
from project.models import AccessPolicy, DUASignature, DataAccessRequest, PublishedProject
from user.models import Training, TrainingType


def get_accessible_projects(user):
    """
    Returns query filter for published projects accessible by a specified user
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

    # add projects that are accessible through events
    events_all = Event.objects.filter(Q(host=user) | Q(participants__user=user))
    active_events = set(events_all.filter(end_date__gte=datetime.now()))
    accessible_datasets = EventDataset.objects.filter(event__in=active_events, is_active=True)
    accessible_projects_ids = []
    for event_dataset in accessible_datasets:
        if event_dataset.has_access(user):
            accessible_projects_ids.append(event_dataset.dataset.id)
    query |= Q(id__in=accessible_projects_ids)

    return PublishedProject.objects.filter(query).distinct()


def can_access_project(project, user):
    """Checks if the project is accessible by the user"""
    if project.deprecated_files:
        return False

    if not project.allow_file_downloads:
        return False

    if project.access_policy == AccessPolicy.OPEN:
        return True
    elif project.access_policy == AccessPolicy.RESTRICTED:
        return user.is_authenticated and DUASignature.objects.filter(project=project, user=user).exists()
    elif project.access_policy == AccessPolicy.CREDENTIALED:
        return (
            user.is_authenticated
            and user.is_credentialed
            and DUASignature.objects.filter(project=project, user=user).exists()
            and Training.objects.get_valid()
            .filter(training_type__in=project.required_trainings.all(), user=user)
            .count()
            == project.required_trainings.count()
        )
    elif project.access_policy == AccessPolicy.CONTRIBUTOR_REVIEW:
        return (
            user.is_authenticated
            and user.is_credentialed
            and DataAccessRequest.objects.get_active(
                project=project,
                requester=user,
                status=DataAccessRequest.ACCEPT_REQUEST_VALUE
            ).exists()
            and Training.objects.get_valid()
            .filter(training_type__in=project.required_trainings.all(), user=user)
            .count()
            == project.required_trainings.count()
        )
    return False
