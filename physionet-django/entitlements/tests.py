from datetime import timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from oauth.models import Partner
from oauth2_provider.models import get_access_token_model, get_application_model

from physionet.enums import LogCategory
from project.models import (
    AccessPolicy, DUASignature, DataAccessRequest, PublishedProject,
)
from user.enums import TrainingStatus
from user.models import Training, TrainingType

from entitlements.serializers import build_response_payload
from entitlements.services import EntitlementResult, check_entitlement

User = get_user_model()
AccessToken = get_access_token_model()
Application = get_application_model()


class AppRegistrationTest(TestCase):
    def test_entitlements_app_registered(self):
        self.assertTrue(apps.is_installed('entitlements'))

    def test_entitlement_check_log_category_exists(self):
        self.assertTrue(hasattr(LogCategory, 'ENTITLEMENT_CHECK'))
        self.assertEqual(LogCategory.ENTITLEMENT_CHECK.value, 'Entitlement Check')
        choice_values = {value for _, value in LogCategory.choices()}
        self.assertIn('Entitlement Check', choice_values)


class EntitlementServiceTest(TestCase):
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        self.user = User.objects.get(username='admin')
        self.open_project = PublishedProject.objects.filter(
            access_policy=AccessPolicy.OPEN
        ).first()
        self.restricted_project = PublishedProject.objects.filter(
            access_policy=AccessPolicy.RESTRICTED
        ).first()
        self.credentialed_project = PublishedProject.objects.filter(
            access_policy=AccessPolicy.CREDENTIALED
        ).first()
        if self.open_project is None:
            self.skipTest('fixtures lack OPEN project')
        if self.credentialed_project is None:
            self.skipTest('fixtures lack CREDENTIALED project')

    # ----- OPEN policy -----
    def test_open_project_granted_for_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        result = check_entitlement(AnonymousUser(), self.open_project)
        self.assertIsInstance(result, EntitlementResult)
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason_code, 'granted')
        self.assertEqual(result.missing_requirements, [])

    def test_deprecated_files_denied(self):
        self.open_project.deprecated_files = True
        self.open_project.save()
        result = check_entitlement(self.user, self.open_project)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason_code, 'deprecated_files')

    # ----- RESTRICTED policy -----
    def test_restricted_denied_when_dua_unsigned(self):
        if self.restricted_project is None:
            self.skipTest('fixtures lack RESTRICTED project')
        DUASignature.objects.filter(
            project=self.restricted_project, user=self.user
        ).delete()
        result = check_entitlement(self.user, self.restricted_project)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason_code, 'dua_not_signed')
        self.assertIn('dua_not_signed', result.missing_requirements)

    def test_restricted_granted_when_dua_signed(self):
        if self.restricted_project is None:
            self.skipTest('fixtures lack RESTRICTED project')
        DUASignature.objects.update_or_create(
            project=self.restricted_project, user=self.user
        )
        result = check_entitlement(self.user, self.restricted_project)
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason_code, 'granted')

    # ----- CREDENTIALED policy -----
    def test_credentialed_denied_when_user_not_credentialed(self):
        self.user.is_credentialed = False
        self.user.save()
        DUASignature.objects.update_or_create(
            project=self.credentialed_project, user=self.user
        )
        result = check_entitlement(self.user, self.credentialed_project)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason_code, 'not_credentialed')
        self.assertIn('not_credentialed', result.missing_requirements)

    def test_credentialed_denied_lists_all_missing(self):
        self.user.is_credentialed = False
        self.user.save()
        DUASignature.objects.filter(
            project=self.credentialed_project, user=self.user
        ).delete()
        if not self.credentialed_project.required_trainings.exists():
            tt = TrainingType.objects.create(
                name='ZZ Test Training', slug='zz-test-training', required_field=0,
            )
            self.credentialed_project.required_trainings.add(tt)
        result = check_entitlement(self.user, self.credentialed_project)
        self.assertFalse(result.allowed)
        # primary reason follows the documented ordering: not_credentialed beats dua_not_signed
        self.assertEqual(result.reason_code, 'not_credentialed')
        self.assertIn('dua_not_signed', result.missing_requirements)
        self.assertIn('not_credentialed', result.missing_requirements)
        self.assertIn('training_incomplete', result.missing_requirements)

    def test_credentialed_granted_when_all_satisfied(self):
        self.user.is_credentialed = True
        self.user.credential_datetime = timezone.now()
        self.user.save()
        DUASignature.objects.update_or_create(
            project=self.credentialed_project, user=self.user
        )
        for tt in self.credentialed_project.required_trainings.all():
            Training.objects.update_or_create(
                user=self.user, training_type=tt,
                defaults={
                    'status': TrainingStatus.ACCEPTED,
                    'process_datetime': timezone.now(),
                },
            )
        result = check_entitlement(self.user, self.credentialed_project)
        self.assertTrue(result.allowed, msg=result.missing_requirements)
        self.assertEqual(result.reason_code, 'granted')
        self.assertEqual(result.missing_requirements, [])
        self.assertEqual(result.missing_training_types, [])

    def test_anonymous_user_on_restricted_returns_not_authenticated(self):
        if self.restricted_project is None:
            self.skipTest('fixtures lack RESTRICTED project')
        from django.contrib.auth.models import AnonymousUser
        result = check_entitlement(AnonymousUser(), self.restricted_project)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason_code, 'not_authenticated')


class EntitlementResponsePayloadTest(TestCase):
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        self.user = User.objects.get(username='admin')
        self.project = PublishedProject.objects.first()

    def test_payload_keys_when_granted(self):
        result = EntitlementResult(allowed=True, reason_code='granted')
        payload = build_response_payload(result, self.user, self.project)
        for key in ('allowed', 'reason_code', 'missing_requirements',
                    'user', 'project', 'partner', 'checked_at'):
            self.assertIn(key, payload)
        # partner is None when not provided (legacy first-party token)
        self.assertIsNone(payload['partner'])
        self.assertTrue(payload['allowed'])
        self.assertEqual(payload['reason_code'], 'granted')
        self.assertEqual(payload['missing_requirements'], [])
        self.assertEqual(
            payload['user']['public_user_uuid'],
            str(self.user.public_user_uuid),
        )
        self.assertEqual(payload['project']['slug'], self.project.slug)
        self.assertEqual(payload['project']['version'], self.project.version)
        self.assertEqual(
            payload['project']['public_project_uuid'],
            str(self.project.public_project_uuid),
        )
        self.assertIn(payload['project']['access_policy'],
                      {'OPEN', 'RESTRICTED', 'CREDENTIALED', 'CONTRIBUTOR_REVIEW'})

    def test_payload_when_denied_carries_reasons(self):
        result = EntitlementResult(
            allowed=False, reason_code='dua_not_signed',
            missing_requirements=['dua_not_signed', 'training_incomplete'],
            missing_training_types=['citi-data-or-specimens-only-research'],
        )
        payload = build_response_payload(result, self.user, self.project)
        self.assertFalse(payload['allowed'])
        self.assertEqual(payload['reason_code'], 'dua_not_signed')
        self.assertEqual(
            payload['missing_requirements'],
            ['dua_not_signed', 'training_incomplete'],
        )
        self.assertEqual(
            payload['missing_training_types'],
            ['citi-data-or-specimens-only-research'],
        )


def _make_partner_with_token(*, user, scope='data:download',
                             organization_name='Partner KHDP',
                             status=Partner.Status.ACTIVE,
                             token_value='partner-token-abc'):
    """Create an Application + Partner + AccessToken triple for tests.

    Mirrors the production wiring done by console.views.partner_new.
    """
    suffix = organization_name.replace(' ', '_').lower()
    dev = User.objects.create_user(
        username=f'dev_{suffix}_{token_value}'[:30],
        email=f'{suffix}_{token_value}@example.com',
        password='pw',
    )
    app = Application.objects.create(
        name=organization_name,
        user=dev,
        redirect_uris='http://localhost',
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
    )
    partner = Partner.objects.create(
        application=app,
        organization_name=organization_name,
        allowed_scopes=[scope],
        status=status,
        created_by=dev,
    )
    token = AccessToken.objects.create(
        user=user, scope=scope,
        expires=timezone.now() + timedelta(seconds=300),
        token=token_value, application=app,
    )
    return partner, app, token


class EntitlementCheckEndpointTest(TestCase):
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        self.user = User.objects.get(username='admin')
        self.project = PublishedProject.objects.filter(
            access_policy=AccessPolicy.OPEN
        ).first()
        if self.project is None:
            self.skipTest('fixtures lack OPEN project')
        self.partner, self.application, self.token = _make_partner_with_token(
            user=self.user,
        )

    def _auth_header(self, token=None):
        return {'HTTP_AUTHORIZATION': f'Bearer {token or self.token.token}'}

    def test_unauthenticated_returns_401(self):
        response = self.client.get('/api/v1/entitlements/check/',
                                   {'project_slug': self.project.slug,
                                    'version': self.project.version})
        self.assertEqual(response.status_code, 401)

    def test_token_without_data_download_scope_returns_403(self):
        self.token.scope = 'profile:read'
        self.token.save()
        response = self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': self.project.slug,
             'version': self.project.version},
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_project_params_returns_400(self):
        response = self.client.get(
            '/api/v1/entitlements/check/', **self._auth_header(),
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn('error', body)

    def test_unknown_project_returns_404(self):
        response = self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': 'no-such-project', 'version': '1.0'},
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, 404)

    def test_open_project_grants_with_valid_token(self):
        response = self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': self.project.slug,
             'version': self.project.version},
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['allowed'])
        self.assertEqual(body['reason_code'], 'granted')
        self.assertEqual(body['project']['slug'], self.project.slug)
        self.assertEqual(body['user']['public_user_uuid'],
                         str(self.user.public_user_uuid))

    def test_lookup_by_public_project_uuid(self):
        response = self.client.get(
            '/api/v1/entitlements/check/',
            {'public_project_uuid': str(self.project.public_project_uuid)},
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['project']['public_project_uuid'],
                         str(self.project.public_project_uuid))

    def test_slug_only_resolves_latest_version(self):
        response = self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': self.project.slug},
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['project']['slug'], self.project.slug)

    def test_suspended_partner_rejected(self):
        self.partner.status = Partner.Status.SUSPENDED
        self.partner.save()
        response = self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': self.project.slug,
             'version': self.project.version},
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['reason_code'], 'partner_suspended')

    def test_revoked_partner_rejected(self):
        self.partner.status = Partner.Status.REVOKED
        self.partner.save()
        response = self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': self.project.slug,
             'version': self.project.version},
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['reason_code'], 'partner_revoked')

    def test_response_payload_includes_partner_identity(self):
        response = self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': self.project.slug,
             'version': self.project.version},
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn('partner', body)
        self.assertEqual(body['partner']['organization_name'],
                         self.partner.organization_name)


class EntitlementCheckLoggingTest(TestCase):
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        from project.models import EntitlementCheckLog
        self.EntitlementCheckLog = EntitlementCheckLog
        self.user = User.objects.get(username='admin')
        self.project = PublishedProject.objects.filter(
            access_policy=AccessPolicy.OPEN
        ).first()
        if self.project is None:
            self.skipTest('fixtures lack OPEN project')
        self.partner, self.application, self.token = _make_partner_with_token(
            user=self.user, organization_name='LogPartner',
            token_value='log-token',
        )

    def test_granted_check_writes_log_row(self):
        before = self.EntitlementCheckLog.objects.count()
        self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': self.project.slug, 'version': self.project.version},
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}',
        )
        after = self.EntitlementCheckLog.objects.count()
        self.assertEqual(after, before + 1)
        log = self.EntitlementCheckLog.objects.latest('creation_datetime')
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.project, self.project)
        self.assertIn('allowed=True', log.data)
        self.assertIn('reason=granted', log.data)
        self.assertIn(f'partner_id={self.partner.pk};', log.data)
        self.assertIn('partner_org=LogPartner', log.data)

    def test_denied_check_also_writes_log(self):
        cred = PublishedProject.objects.filter(
            access_policy=AccessPolicy.CREDENTIALED
        ).first()
        if cred is None:
            self.skipTest('No CREDENTIALED fixture project available')
        DUASignature.objects.filter(project=cred, user=self.user).delete()
        before = self.EntitlementCheckLog.objects.count()
        self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': cred.slug, 'version': cred.version},
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}',
        )
        after = self.EntitlementCheckLog.objects.count()
        self.assertEqual(after, before + 1)
        log = self.EntitlementCheckLog.objects.latest('creation_datetime')
        self.assertIn('allowed=False', log.data)

    def test_lookup_failures_do_not_log(self):
        before = self.EntitlementCheckLog.objects.count()
        self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': 'nope', 'version': '0'},
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}',
        )
        self.assertEqual(self.EntitlementCheckLog.objects.count(), before)


from django.test.utils import override_settings


@override_settings(
    REST_FRAMEWORK={
        'DEFAULT_AUTHENTICATION_CLASSES': [
            'oauth2_provider.contrib.rest_framework.OAuth2Authentication',
        ],
        'DEFAULT_THROTTLE_RATES': {
            'entitlement_check': '2/min',
        },
    },
)
class EntitlementCheckThrottleTest(TestCase):
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        self.user = User.objects.get(username='admin')
        self.project = PublishedProject.objects.filter(
            access_policy=AccessPolicy.OPEN
        ).first()
        if self.project is None:
            self.skipTest('fixtures lack OPEN project')
        self.partner, self.application, self.token = _make_partner_with_token(
            user=self.user, organization_name='ThrottlePartner',
            token_value='throttle-token',
        )

    def test_third_request_is_throttled(self):
        from django.core.cache import cache
        cache.clear()
        url = '/api/v1/entitlements/check/'
        params = {'project_slug': self.project.slug, 'version': self.project.version}
        hdr = {'HTTP_AUTHORIZATION': f'Bearer {self.token.token}'}
        self.assertEqual(self.client.get(url, params, **hdr).status_code, 200)
        self.assertEqual(self.client.get(url, params, **hdr).status_code, 200)
        self.assertEqual(self.client.get(url, params, **hdr).status_code, 429)

    def test_two_tokens_same_user_have_independent_buckets(self):
        """Per-token (not per-user) throttling: a second token for the same
        user must not consume the first token's bucket."""
        from django.core.cache import cache
        cache.clear()
        second_partner, _, second_token = _make_partner_with_token(
            user=self.user, organization_name='SecondPartner',
            token_value='second-throttle-token',
        )
        url = '/api/v1/entitlements/check/'
        params = {'project_slug': self.project.slug, 'version': self.project.version}
        hdr1 = {'HTTP_AUTHORIZATION': f'Bearer {self.token.token}'}
        hdr2 = {'HTTP_AUTHORIZATION': f'Bearer {second_token.token}'}
        # Burn token1's 2/min budget
        self.assertEqual(self.client.get(url, params, **hdr1).status_code, 200)
        self.assertEqual(self.client.get(url, params, **hdr1).status_code, 200)
        self.assertEqual(self.client.get(url, params, **hdr1).status_code, 429)
        # token2 should still work — independent bucket
        self.assertEqual(self.client.get(url, params, **hdr2).status_code, 200)


from django.contrib.auth.models import Permission


class EntitlementConsolePageTest(TestCase):
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        self.admin = User.objects.create_user(
            username='ent_admin', email='ea@example.com', password='pw',
            is_active=True,
        )
        self.admin.user_permissions.add(
            Permission.objects.get(codename='change_partner'),
        )
        self.client.force_login(self.admin)

    def test_admin_can_view_global_entitlement_logs_page(self):
        response = self.client.get('/console/entitlement-check-logs/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Entitlement', response.content)

    def test_non_admin_redirected_or_forbidden(self):
        self.client.logout()
        plain = User.objects.create_user(
            username='plain', email='p@example.com', password='pw',
            is_active=True,
        )
        self.client.force_login(plain)
        response = self.client.get('/console/entitlement-check-logs/')
        self.assertIn(response.status_code, (302, 403))

    def test_partner_detail_page_shows_api_usage_panel(self):
        researcher = User.objects.get(username='admin')
        partner, _, token = _make_partner_with_token(
            user=researcher, organization_name='ConsoleTestPartner',
            token_value='console-test-token',
        )
        # Drive one log row through the API
        self.client.logout()
        project = PublishedProject.objects.filter(
            access_policy=AccessPolicy.OPEN
        ).first()
        if project is None:
            self.skipTest('fixtures lack OPEN project')
        self.client.get(
            '/api/v1/entitlements/check/',
            {'project_slug': project.slug},
            HTTP_AUTHORIZATION=f'Bearer {token.token}',
        )
        # Re-login as admin to view the panel
        self.client.force_login(self.admin)
        response = self.client.get(f'/console/partners/{partner.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Entitlement check', response.content)


class AccessibleProjectsEndpointTest(TestCase):
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        self.user = User.objects.get(username='admin')
        self.partner, self.application, self.token = _make_partner_with_token(
            user=self.user, organization_name='ListPartner',
            token_value='list-token',
        )

    def _hdr(self, token=None):
        return {'HTTP_AUTHORIZATION': f'Bearer {token or self.token.token}'}

    def test_unauthenticated_returns_401(self):
        response = self.client.get('/api/v1/entitlements/accessible-projects/')
        self.assertEqual(response.status_code, 401)

    def test_token_without_scope_returns_403(self):
        self.token.scope = 'profile:read'
        self.token.save()
        response = self.client.get(
            '/api/v1/entitlements/accessible-projects/', **self._hdr(),
        )
        self.assertEqual(response.status_code, 403)

    def test_returns_only_open_for_anonymous_equivalent(self):
        """A regular authenticated user with no DUAs/training sees only OPEN projects."""
        plain = User.objects.create_user(
            username='plain_lister', email='pl@example.com', password='pw',
            is_active=True,
        )
        _, _, plain_token = _make_partner_with_token(
            user=plain, organization_name='PlainPartner',
            token_value='plain-list-token',
        )
        response = self.client.get(
            '/api/v1/entitlements/accessible-projects/',
            HTTP_AUTHORIZATION=f'Bearer {plain_token.token}',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for item in body['results']:
            self.assertEqual(item['access_policy'], 'Open')

    def test_response_envelope_includes_user_and_partner(self):
        response = self.client.get(
            '/api/v1/entitlements/accessible-projects/', **self._hdr(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ('count', 'results', 'user', 'partner', 'checked_at'):
            self.assertIn(key, body)
        self.assertEqual(body['user']['public_user_uuid'],
                         str(self.user.public_user_uuid))
        self.assertEqual(body['partner']['organization_name'], 'ListPartner')

    def test_pagination_limit_offset(self):
        response = self.client.get(
            '/api/v1/entitlements/accessible-projects/?limit=1',
            **self._hdr(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertLessEqual(len(body['results']), 1)
        if body['count'] > 1:
            self.assertIsNotNone(body['next'])

    def test_suspended_partner_rejected(self):
        self.partner.status = Partner.Status.SUSPENDED
        self.partner.save()
        response = self.client.get(
            '/api/v1/entitlements/accessible-projects/', **self._hdr(),
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body['allowed'])
        self.assertEqual(body['reason_code'], 'partner_suspended')
        self.assertEqual(body['missing_requirements'], ['partner_suspended'])

    def test_writes_one_audit_log_per_call(self):
        from project.models import EntitlementCheckLog
        before = EntitlementCheckLog.objects.filter(
            data__contains='reason=list_returned'
        ).count()
        self.client.get(
            '/api/v1/entitlements/accessible-projects/', **self._hdr(),
        )
        after = EntitlementCheckLog.objects.filter(
            data__contains='reason=list_returned'
        ).count()
        self.assertEqual(after, before + 1)
        log = EntitlementCheckLog.objects.filter(
            data__contains='reason=list_returned'
        ).latest('creation_datetime')
        self.assertIn(f'partner_id={self.partner.pk};', log.data)
        self.assertIn('count=', log.data)

    def test_excludes_deprecated_projects_from_list(self):
        """A deprecated project the user otherwise has access to must not
        appear in /accessible-projects/."""
        project = PublishedProject.objects.filter(
            access_policy=AccessPolicy.OPEN
        ).first()
        if project is None:
            self.skipTest('fixtures lack OPEN project')
        project.deprecated_files = True
        project.save()
        response = self.client.get(
            '/api/v1/entitlements/accessible-projects/', **self._hdr(),
        )
        self.assertEqual(response.status_code, 200)
        slugs = [item['slug'] for item in response.json()['results']]
        self.assertNotIn(project.slug, slugs)


class EntitlementLogAggregateRowTest(TestCase):
    fixtures = ['demo-user', 'demo-project']

    def setUp(self):
        from project.models import EntitlementCheckLog
        self.EntitlementCheckLog = EntitlementCheckLog
        self.user = User.objects.get(username='admin')
        self.partner, _, self.token = _make_partner_with_token(
            user=self.user, organization_name='AggLogPartner',
            token_value='agg-log-token',
        )

    def test_accessible_projects_log_has_null_project_and_str_does_not_crash(self):
        self.client.get(
            '/api/v1/entitlements/accessible-projects/',
            HTTP_AUTHORIZATION=f'Bearer {self.token.token}',
        )
        log = self.EntitlementCheckLog.objects.filter(
            data__contains='reason=list_returned'
        ).latest('creation_datetime')
        self.assertIsNone(log.content_type_id)
        self.assertIsNone(log.object_id)
        self.assertIsNone(log.project)
        # __str__ must render without crashing
        self.assertIn('aggregate', str(log))
