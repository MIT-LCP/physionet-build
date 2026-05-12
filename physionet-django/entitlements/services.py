"""Entitlement check service.

Pure function answering: is this user entitled to access this published
project, and if not, why? Wraps `project.authorization.access.can_access_project`
to keep the bool source of truth identical, then re-derives reason codes
when access is denied so partner platforms can render actionable messages
to users.
"""
import logging
from dataclasses import dataclass, field
from typing import List

from django.conf import settings

from project.authorization.access import can_access_project
from project.models import (
    AccessPolicy, DUASignature, DataAccessRequest, PublishedProject,
)
from user.models import Training
from physionet.utility import get_client_ip, get_country_code

logger = logging.getLogger(__name__)


# Closed set of reason codes. Partners depend on these strings; do not rename
# without coordinating a versioned API change.
GRANTED = 'granted'
DEPRECATED_FILES = 'deprecated_files'
GEORESTRICTED = 'georestricted'
NOT_AUTHENTICATED = 'not_authenticated'
DUA_NOT_SIGNED = 'dua_not_signed'
NOT_CREDENTIALED = 'not_credentialed'
TRAINING_INCOMPLETE = 'training_incomplete'
DATA_ACCESS_REQUEST_REQUIRED = 'data_access_request_required'

# Order in which we report the *primary* reason when multiple gates fail.
REASON_PRIORITY = [
    DEPRECATED_FILES,
    GEORESTRICTED,
    NOT_AUTHENTICATED,
    NOT_CREDENTIALED,
    DUA_NOT_SIGNED,
    DATA_ACCESS_REQUEST_REQUIRED,
    TRAINING_INCOMPLETE,
]


@dataclass
class EntitlementResult:
    allowed: bool
    reason_code: str
    missing_requirements: List[str] = field(default_factory=list)
    missing_training_types: List[str] = field(default_factory=list)


def _missing_required_trainings(user, project: PublishedProject) -> List[str]:
    required = list(project.required_trainings.values_list('slug', flat=True))
    if not required:
        return []
    valid = (
        Training.objects.get_valid()
        .filter(user=user, training_type__slug__in=required)
        .values_list('training_type__slug', flat=True)
    )
    valid_set = set(valid)
    return [slug for slug in required if slug not in valid_set]


def check_entitlement(user, project: PublishedProject, request=None) -> EntitlementResult:
    """Return structured entitlement result for (user, project).

    Mirrors the bool decision of `can_access_project` exactly, but adds
    reason codes when access is denied. `request` is optional and only
    used for georestriction (matches existing behavior of
    can_access_project when request=None: georestriction is skipped).
    Note: when called without a request on a georestricted project, the
    response will not surface `georestricted` as the denial reason —
    callers that care about georestriction must pass `request`.
    """
    if can_access_project(project, user, request):
        return EntitlementResult(allowed=True, reason_code=GRANTED)

    if project.deprecated_files:
        return EntitlementResult(
            allowed=False, reason_code=DEPRECATED_FILES,
            missing_requirements=[DEPRECATED_FILES],
        )

    if project.georestricted and request is not None:
        country = get_country_code(get_client_ip(request))
        if country in settings.BLOCKED_REGIONS:
            return EntitlementResult(
                allowed=False, reason_code=GEORESTRICTED,
                missing_requirements=[GEORESTRICTED],
            )

    if not user.is_authenticated:
        return EntitlementResult(
            allowed=False, reason_code=NOT_AUTHENTICATED,
            missing_requirements=[NOT_AUTHENTICATED],
        )

    missing: List[str] = []
    missing_training: List[str] = []
    policy = project.access_policy

    if policy == AccessPolicy.RESTRICTED:
        if not DUASignature.objects.filter(project=project, user=user).exists():
            missing.append(DUA_NOT_SIGNED)

    elif policy == AccessPolicy.CREDENTIALED:
        if not user.is_credentialed:
            missing.append(NOT_CREDENTIALED)
        if not DUASignature.objects.filter(project=project, user=user).exists():
            missing.append(DUA_NOT_SIGNED)
        missing_training = _missing_required_trainings(user, project)
        if missing_training:
            missing.append(TRAINING_INCOMPLETE)

    elif policy == AccessPolicy.CONTRIBUTOR_REVIEW:
        if not user.is_credentialed:
            missing.append(NOT_CREDENTIALED)
        approved = DataAccessRequest.objects.get_active(
            project=project, requester=user,
            status=DataAccessRequest.ACCEPT_REQUEST_VALUE,
        ).exists()
        if not approved:
            missing.append(DATA_ACCESS_REQUEST_REQUIRED)
        missing_training = _missing_required_trainings(user, project)
        if missing_training:
            missing.append(TRAINING_INCOMPLETE)

    if not missing:
        # can_access_project said False but our policy ladder found no
        # specific reason — indicates the two have drifted out of sync.
        # Log loudly and fall back to a generic denial so partners still
        # get a structured response rather than a 500.
        logger.error(
            'check_entitlement: can_access_project returned False but no '
            'reason matched for user=%s project=%s policy=%s. '
            'Service is out of sync with project.authorization.access.',
            getattr(user, 'pk', None), project.pk, policy,
        )
        missing = [NOT_AUTHENTICATED]

    primary = next((r for r in REASON_PRIORITY if r in missing), missing[0])
    missing_training_types = (
        missing_training if TRAINING_INCOMPLETE in missing else []
    )
    return EntitlementResult(
        allowed=False, reason_code=primary,
        missing_requirements=missing,
        missing_training_types=missing_training_types,
    )
