"""Response payload construction for the entitlement check endpoint.

We build a plain dict (not a DRF Serializer) because the result composes
data from three different objects (user, project, EntitlementResult) and
DRF's nested-source plumbing adds noise without value at this size.
"""
from django.utils import timezone

from project.enums import AccessPolicy

from entitlements.services import EntitlementResult


def _access_policy_name(value: int) -> str:
    try:
        return AccessPolicy(value).name
    except ValueError:
        return 'UNKNOWN'


def build_response_payload(result: EntitlementResult, user, project,
                           partner=None) -> dict:
    return {
        'allowed': result.allowed,
        'reason_code': result.reason_code,
        'missing_requirements': list(result.missing_requirements),
        'missing_training_types': list(result.missing_training_types),
        'user': {
            'public_user_uuid': (
                str(user.public_user_uuid) if user.is_authenticated else None
            ),
        },
        'project': {
            'slug': project.slug,
            'version': project.version,
            'public_project_uuid': str(project.public_project_uuid),
            'access_policy': _access_policy_name(project.access_policy),
        },
        'partner': (
            {'organization_name': partner.organization_name}
            if partner is not None else None
        ),
        'checked_at': timezone.now().isoformat(),
    }
