from datetime import datetime

from django.db.models import Q
from django.conf import settings

from events.models import Event, EventDataset
from project.authorization.events import has_access_to_event_dataset
from project.models import AccessPolicy, DUASignature, DataAccessRequest, PublishedProject
from user.models import CredentialApplication, Training, TrainingType
from physionet.utility import get_country_code, get_client_ip


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


def has_required_trainings(project, user):
    """
    Returns True if the user has a valid training of every type the project requires.
    """
    required_trainings = project.required_trainings.all()
    completed_types = (
        Training.objects.get_valid()
        .filter(training_type__in=required_trainings, user=user)
        .values('training_type')
        .distinct()
        .count()
    )
    return completed_types == required_trainings.count()


def can_access_project(project, user, request=None):
    """
    Checks if the project is accessible by the user
    Users may access a project through different ways, for example, thorough direct download on the physionet website,
    or through s3 bucket links, or gcs storage.
    This function only checks access to the project in general, users might still not be able to access the files
    even if they can access the project.

    Args:
        project: The project instance
        user: The user requesting access
        request: The HTTP request object (optional, needed for country-based restrictions)
    """
    if project.deprecated_files:
        return False

    if is_region_blocked(project, request):
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
            and has_required_trainings(project, user)
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
            and has_required_trainings(project, user)
        )
    return False


def login_required_for_download(user):
    """
    Whether the user must sign in before downloading any project files.

    Set by REQUIRE_LOGIN_FOR_DOWNLOAD, which also covers open-access projects.
    """
    return settings.REQUIRE_LOGIN_FOR_DOWNLOAD and not user.is_authenticated


def can_view_project_files(project, user, request=None):
    """
    Checks if the project files are  directly accessible by the user
    Currently used to allow direct file downloads and to show project files on the platform
    """
    if login_required_for_download(user):
        return False
    return can_access_project(project, user, request) and project.allow_file_downloads


def is_region_blocked(project, request=None):
    """
    Returns True if the project is georestricted and the request comes from a blocked region.
    Without a request, the region is unknown and nothing is blocked.
    """
    if not (project.georestricted and request):
        return False
    return get_country_code(get_client_ip(request)) in settings.BLOCKED_REGIONS


class RequirementStatus:
    COMPLETE = 'complete'
    PENDING = 'pending'
    REQUIRED = 'required'
    UNKNOWN = 'unknown'


def get_access_requirements(project, user):
    """
    Lists the standard steps a user must complete to access a project.

    Describes the same access path that can_access_project checks, step by step, so that
    users can see what is missing. It does not grant access.

    Returns a list of dicts with:
        id: unique within the list (each required training has its own id)
        code: the kind of step (sign_in, credentialing, training, dua or review)
        label: human-readable name
        status: a RequirementStatus value; UNKNOWN means the user is anonymous
    """
    policy = project.access_policy
    signed_in = user.is_authenticated
    requirements = []

    def add(item_id, code, label, done, pending=False):
        if done:
            state = RequirementStatus.COMPLETE
        elif pending:
            state = RequirementStatus.PENDING
        elif signed_in:
            state = RequirementStatus.REQUIRED
        else:
            state = RequirementStatus.UNKNOWN
        requirements.append({'id': item_id, 'code': code, 'label': label, 'status': state})

    if policy == AccessPolicy.OPEN:
        return requirements

    requirements.append({
        'id': 'sign_in', 'code': 'sign_in', 'label': 'Sign in to PhysioNet',
        'status': RequirementStatus.COMPLETE if signed_in else RequirementStatus.REQUIRED,
    })

    if policy in (AccessPolicy.CREDENTIALED, AccessPolicy.CONTRIBUTOR_REVIEW):
        add('credentialing', 'credentialing', 'PhysioNet credentialing',
            done=signed_in and user.is_credentialed,
            pending=signed_in and CredentialApplication.objects.filter(
                user=user, status=CredentialApplication.Status.PENDING
            ).exists())

        training_types = list(project.required_trainings.all())
        valid_ids, pending_ids = set(), set()
        if signed_in and training_types:
            user_trainings = Training.objects.filter(user=user, training_type__in=training_types)
            valid_ids = set(user_trainings.get_valid().values_list('training_type_id', flat=True))
            for pending in (user_trainings.get_review(), user_trainings.get_in_progress()):
                pending_ids.update(pending.values_list('training_type_id', flat=True))
        for training_type in training_types:
            add(f'training:{training_type.pk}', 'training', training_type.name,
                done=training_type.pk in valid_ids,
                pending=training_type.pk in pending_ids)

    if policy in (AccessPolicy.RESTRICTED, AccessPolicy.CREDENTIALED):
        add('dua', 'dua', 'Data use agreement',
            done=signed_in and DUASignature.objects.filter(project=project, user=user).exists())

    if policy == AccessPolicy.CONTRIBUTOR_REVIEW:
        requests = DataAccessRequest.objects.filter(project=project, requester=user) if signed_in else None
        add('review', 'review', 'Contributor approval and data use agreement',
            done=signed_in and requests.get_active().exists(),
            pending=signed_in and requests.filter(status=DataAccessRequest.PENDING_VALUE).exists())

    return requirements
