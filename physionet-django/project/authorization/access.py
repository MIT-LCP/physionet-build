from datetime import datetime

from django.db.models import Q

from events.models import Event, EventDataset
from project.authorization.events import has_access_to_event_dataset
from project.models import AccessPolicy, DUASignature, DataAccessRequest, PublishedProject
from user.models import Training, TrainingType


def get_public_projects_query():
    """Returns query filter for public published projects"""
    return Q(access_policy=AccessPolicy.OPEN)


def get_restricted_projects_query(user):
    """Returns query filter for restricted published projects accessible by a specified user"""
    dua_signatures = DUASignature.objects.filter(user=user)
    query = Q(access_policy=AccessPolicy.RESTRICTED) & Q(duasignature__in=dua_signatures)
    return query


def get_credentialed_projects_query(user):
    """Returns query filter for credentialed published projects accessible by a specified user"""
    dua_signatures = DUASignature.objects.filter(user=user)

    completed_training = (
        Training.objects.get_valid()
        .filter(user=user)
        .values_list("training_type")
    )
    not_completed_training = TrainingType.objects.exclude(pk__in=completed_training)
    required_training_complete = ~Q(required_trainings__in=not_completed_training)

    accepted_data_access_requests = DataAccessRequest.objects.filter(
        requester=user, status=DataAccessRequest.ACCEPT_REQUEST_VALUE
    )

    contributor_review_with_access = Q(
        access_policy=AccessPolicy.CONTRIBUTOR_REVIEW
    ) & Q(data_access_requests__in=accepted_data_access_requests)

    credentialed_with_dua_signed = Q(
        access_policy=AccessPolicy.CREDENTIALED
    ) & Q(duasignature__in=dua_signatures)

    query = required_training_complete & (
        contributor_review_with_access | credentialed_with_dua_signed
    )
    return query


def get_projects_accessible_through_events(user):
    """Returns query filter for published projects accessible by a specified user through events"""
    events_all = Event.objects.filter(Q(host=user) | Q(participants__user=user))

    active_events = set(events_all.filter(end_date__gte=datetime.now()))

    accessible_datasets = EventDataset.objects.filter(event__in=active_events, is_active=True)

    accessible_projects_ids = []
    for event_dataset in accessible_datasets:
        if has_access_to_event_dataset(user, event_dataset):
            accessible_projects_ids.append(event_dataset.dataset.id)

    query = Q(id__in=accessible_projects_ids)
    return query


def get_accessible_projects(user):
    """
    Returns all published projects accessible by a specified user
    """
    query = Q(deprecated_files=False)

    query &= get_public_projects_query()

    if user.is_authenticated:
        query |= get_restricted_projects_query(user)

    if user.is_credentialed:
        query |= get_credentialed_projects_query(user)

    query |= get_projects_accessible_through_events(user)

    return PublishedProject.objects.filter(query).distinct()


def can_access_project(project, user):
    """
    Checks if the project is accessible by the user
    Users may access a project through different ways, for example, thorough direct download on the physionet website,
    or through s3 bucket links, or gcs storage.
    This function only checks access to the project in general, users might still not be able to access the files
    even if they can access the project.
    """
    if project.deprecated_files:
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


def can_view_project_files(project, user):
    """
    Checks if the project files are  directly accessible by the user
    Currently used to allow direct file downloads and to show project files on the platform
    """
    return can_access_project(project, user) and project.allow_file_downloads
