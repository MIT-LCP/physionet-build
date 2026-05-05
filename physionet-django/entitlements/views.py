"""Entitlement check API view.

OAuth2-protected DRF endpoint requiring the `data:download` scope. Looks
up a PublishedProject by slug+version (latest if version omitted) or
public_project_uuid, defends in depth against suspended/revoked partners
(already blocked at /token by oauth.validators.CustomOAuth2Validator,
but pre-existing tokens stay valid until expiry), runs check_entitlement,
writes an audit log, and returns JSON. Rate-limited via UserRateThrottle.
"""
import uuid as uuid_lib

from django.conf import settings as django_settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from oauth2_provider.contrib.rest_framework import (
    OAuth2Authentication, TokenHasScope,
)
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from export.serializers import PublishedProjectSerializer
from oauth.models import Partner
from physionet.utility import get_client_ip, get_country_code
from project.models import EntitlementCheckLog, PublishedProject

from entitlements.serializers import build_response_payload
from entitlements.services import check_entitlement


class EntitlementCheckThrottle(UserRateThrottle):
    """UserRateThrottle that keys per OAuth access token (rather than per
    user) so two partners holding distinct tokens for the same researcher
    do not share one rate-limit bucket. Also re-reads the configured rate
    on each instantiation so test override_settings(REST_FRAMEWORK=...)
    takes effect (the base class caches THROTTLE_RATES at class load).
    """
    scope = 'entitlement_check'

    def get_rate(self):
        rates = api_settings.DEFAULT_THROTTLE_RATES
        try:
            return rates[self.scope]
        except KeyError:
            return None

    def get_cache_key(self, request, view):
        token = request.auth
        if token is None or not getattr(token, 'pk', None):
            return None  # nothing to throttle on
        return self.cache_format % {
            'scope': self.scope,
            'ident': token.pk,
        }


def _resolve_partner(application):
    """Return the Partner for an oauth Application, or None for legacy apps."""
    if application is None:
        return None
    return getattr(application, 'partner', None)


def _resolve_project(params):
    """Look up a PublishedProject by query params.

    Accepts either:
      - ?public_project_uuid=<uuid>
      - ?project_slug=<slug>&version=<version>   (version optional → latest)

    Returns (project, error_response). On success, error_response is None.
    """
    uuid_str = params.get('public_project_uuid')
    if uuid_str:
        try:
            uuid_val = uuid_lib.UUID(uuid_str)
        except ValueError:
            return None, Response(
                {'error': 'public_project_uuid is not a valid UUID'},
                status=400,
            )
        project = PublishedProject.objects.filter(
            public_project_uuid=uuid_val
        ).first()
        if project is None:
            return None, Response({'error': 'project not found'}, status=404)
        return project, None

    slug = params.get('project_slug')
    if not slug:
        return None, Response(
            {'error': 'must provide project_slug (with optional version) '
                      'or public_project_uuid'},
            status=400,
        )
    version = params.get('version')
    qs = PublishedProject.objects.filter(slug=slug)
    if version:
        project = qs.filter(version=version).first()
    else:
        project = qs.filter(is_latest_version=True).first()
    if project is None:
        return None, Response({'error': 'project not found'}, status=404)
    return project, None


class EntitlementCheckView(APIView):
    authentication_classes = [OAuth2Authentication]
    permission_classes = [IsAuthenticated, TokenHasScope]
    required_scopes = ['data:download']
    throttle_classes = [EntitlementCheckThrottle]

    def get(self, request, *args, **kwargs):
        user = request.user
        token = request.auth
        partner = _resolve_partner(token.application if token else None)

        if partner is not None and partner.status != Partner.Status.ACTIVE:
            reason = (
                'partner_suspended'
                if partner.status == Partner.Status.SUSPENDED
                else 'partner_revoked'
            )
            return Response(
                {
                    'allowed': False,
                    'reason_code': reason,
                    'missing_requirements': [reason],
                    'partner': {'organization_name': partner.organization_name},
                },
                status=403,
            )

        project, error = _resolve_project(request.GET)
        if error is not None:
            return error

        result = check_entitlement(user, project, request=request)
        partner_id = partner.pk if partner is not None else ''
        partner_org = partner.organization_name if partner is not None else 'unknown'
        EntitlementCheckLog.objects.create(
            user=user,
            content_type=ContentType.objects.get_for_model(project),
            object_id=project.id,
            data=(
                f'allowed={result.allowed};reason={result.reason_code};'
                f'partner_id={partner_id};partner_org={partner_org};'
                f'version={project.version}'
            ),
        )
        payload = build_response_payload(result, user, project, partner=partner)
        return Response(payload, status=200)


class AccessibleProjectsPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 100


class AccessibleProjectsView(APIView):
    authentication_classes = [OAuth2Authentication]
    permission_classes = [IsAuthenticated, TokenHasScope]
    required_scopes = ['data:download']
    throttle_classes = [EntitlementCheckThrottle]

    def get(self, request, *args, **kwargs):
        user = request.user
        token = request.auth
        partner = _resolve_partner(token.application if token else None)

        if partner is not None and partner.status != Partner.Status.ACTIVE:
            reason = (
                'partner_suspended'
                if partner.status == Partner.Status.SUSPENDED
                else 'partner_revoked'
            )
            return Response(
                {
                    'allowed': False,
                    'reason_code': reason,
                    'missing_requirements': [reason],
                    'partner': {'organization_name': partner.organization_name},
                },
                status=403,
            )

        queryset = (
            PublishedProject.objects.accessible_by(user)
            .filter(deprecated_files=False)
            .order_by('-publish_datetime')
        )
        country = get_country_code(get_client_ip(request))
        if country in django_settings.BLOCKED_REGIONS:
            queryset = queryset.exclude(georestricted=True)
        paginator = AccessibleProjectsPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = PublishedProjectSerializer(
            page, many=True, context={'request': request},
        )
        paginated = paginator.get_paginated_response(serializer.data).data

        partner_id = partner.pk if partner is not None else ''
        partner_org = partner.organization_name if partner is not None else 'unknown'
        EntitlementCheckLog.objects.create(
            user=user,
            content_type=None,
            object_id=None,
            data=(
                f'allowed=True;reason=list_returned;'
                f'partner_id={partner_id};partner_org={partner_org};'
                f'count={paginator.count}'
            ),
        )

        envelope = {
            'count': paginated['count'],
            'next': paginated['next'],
            'previous': paginated['previous'],
            'results': paginated['results'],
            'user': {'public_user_uuid': str(user.public_user_uuid)},
            'partner': (
                {'organization_name': partner.organization_name}
                if partner is not None else None
            ),
            'checked_at': timezone.now().isoformat(),
        }
        return Response(envelope, status=200)
