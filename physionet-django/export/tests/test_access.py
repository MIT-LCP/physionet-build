"""The access API explains requirements without granting access itself."""

import base64
import itertools
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application
from rest_framework.test import APIClient

from project.authorization.access import can_access_project, get_access_requirements
from project.models import AccessPolicy, CoreProject, DataAccessRequest, DUASignature, PublishedProject, ProjectType
from user.enums import RequiredField, TrainingStatus
from oauth.clients import PYTHON_CLIENT_ID
from project.utility import DOWNLOAD_TOKEN_SCOPE
from user.models import CredentialApplication, PersonalAccessToken, Training, TrainingType, User


class ProjectAccessStatusTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()
        kind = ProjectType.objects.create(id=123, name='Access Test Database')
        core = CoreProject.objects.create()
        self.project = PublishedProject.objects.create(
            core_project=core, resource_type=kind, slug='access-test', submission_slug='access-test',
            version='1.0', title='Access Test', access_policy=AccessPolicy.CREDENTIALED,
            is_latest_version=True,
        )
        self.training = TrainingType.objects.create(name='Access Test Training')
        self.project.required_trainings.add(self.training)
        self.user = User.objects.create_user(
            email='access-test@example.com', username='accesstest',
            password='correct-password', is_active=True,
        )

    def url(self, version='1.0'):
        return reverse('published_project_access_status', kwargs={
            'project_slug': self.project.slug, 'version': version,
        })

    def requirements(self, response):
        """Index requirements by code. Only use with projects that need at most one training."""
        items = response.json()['requirements']
        self.assertEqual(len({item['id'] for item in items}), len(items))
        by_code = {item['code']: item for item in items}
        self.assertEqual(len(by_code), len(items))
        return by_code

    def test_anonymous_sees_sign_in_without_exposing_account_state(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['can_download'])
        self.assertEqual(response.json()['status'], 'sign_in_required')
        requirements = self.requirements(response)
        self.assertEqual(requirements['sign_in']['status'], 'required')
        self.assertEqual(requirements['credentialing']['status'], 'unknown')
        self.assertEqual(requirements['training']['status'], 'unknown')
        self.assertEqual(requirements['dua']['status'], 'unknown')

    def test_basic_auth_reports_missing_then_completed_requirements(self):
        token = base64.b64encode(b'accesstest:correct-password').decode('ascii')
        self.client.credentials(HTTP_AUTHORIZATION=f'Basic {token}')
        response = self.client.get(self.url('latest'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['version'], '1.0')
        self.assertEqual(response.json()['status'], 'action_required')
        self.assertEqual(self.requirements(response)['credentialing']['status'], 'required')

        self.user.is_credentialed = True
        self.user.save(update_fields=['is_credentialed'])
        Training.objects.create(
            slug='access-test-training', user=self.user, training_type=self.training,
            status=TrainingStatus.ACCEPTED, process_datetime=timezone.now(),
        )
        DUASignature.objects.create(project=self.project, user=self.user)
        response = self.client.get(self.url())
        self.assertTrue(response.json()['can_download'])
        self.assertEqual(response.json()['status'], 'ready')
        self.assertTrue(all(item['status'] == 'complete' for item in response.json()['requirements']))

    def test_pending_training_is_not_reported_as_complete(self):
        self.client.force_authenticate(self.user)
        Training.objects.create(
            slug='pending-training', user=self.user, training_type=self.training,
            status=TrainingStatus.REVIEW,
        )
        self.assertEqual(self.requirements(self.client.get(self.url()))['training']['status'], 'pending')

    def test_pending_credentialing_application_is_not_reported_as_missing(self):
        CredentialApplication.objects.create(
            slug='pending-access', user=self.user, first_names='Research',
            last_name='User', researcher_category=2, organization_name='MIT',
            job_title='Researcher', city='Boston', country='US', zip_code='02139',
            reference_category=1, reference_name='Colleague',
            reference_email='colleague@example.com', reference_organization='MIT',
        )
        self.client.force_authenticate(self.user)
        response = self.client.get(self.url())
        self.assertEqual(self.requirements(response)['credentialing']['status'], 'pending')

    def test_open_project_and_disabled_downloads(self):
        self.project.access_policy = AccessPolicy.OPEN
        self.project.save(update_fields=['access_policy'])
        response = self.client.get(self.url())
        self.assertEqual(response.json()['status'], 'ready')
        self.assertEqual(response.json()['requirements'], [])
        self.project.allow_file_downloads = False
        self.project.save(update_fields=['allow_file_downloads'])
        response = self.client.get(self.url())
        self.assertFalse(response.json()['can_download'])
        self.assertEqual(response.json()['status'], 'unavailable')
        self.assertEqual(response.json()['reason'], 'downloads_disabled')

    def test_restricted_project_only_requires_sign_in_and_dua(self):
        self.project.access_policy = AccessPolicy.RESTRICTED
        self.project.save(update_fields=['access_policy'])
        self.client.force_authenticate(self.user)
        response = self.client.get(self.url())
        self.assertEqual(set(self.requirements(response)), {'sign_in', 'dua'})
        self.assertEqual(response.json()['status'], 'action_required')
        DUASignature.objects.create(project=self.project, user=self.user)
        self.assertTrue(self.client.get(self.url()).json()['can_download'])

    def test_deprecated_files_are_unavailable_even_with_requirements_complete(self):
        self.project.access_policy = AccessPolicy.OPEN
        self.project.deprecated_files = True
        self.project.save(update_fields=['access_policy', 'deprecated_files'])
        response = self.client.get(self.url())
        self.assertFalse(response.json()['can_download'])
        self.assertEqual(response.json()['status'], 'unavailable')
        self.assertEqual(response.json()['reason'], 'deprecated_files')

    def test_embargoed_files_are_unavailable(self):
        self.project.access_policy = AccessPolicy.OPEN
        self.project.embargo_files_days = 30
        self.project.save(update_fields=['access_policy', 'embargo_files_days'])
        response = self.client.get(self.url())
        self.assertFalse(response.json()['can_download'])
        self.assertEqual(response.json()['status'], 'unavailable')
        self.assertEqual(response.json()['reason'], 'embargoed')

    def test_in_progress_platform_training_is_pending(self):
        self.training.required_field = RequiredField.PLATFORM
        self.training.save(update_fields=['required_field'])
        Training.objects.create(
            slug='in-progress-training', user=self.user, training_type=self.training,
            status=TrainingStatus.IN_PROGRESS,
        )
        self.client.force_authenticate(self.user)
        self.assertEqual(self.requirements(self.client.get(self.url()))['training']['status'], 'pending')

    def test_requirements_disagreeing_with_access_decision_are_logged(self):
        self.client.force_authenticate(self.user)
        complete = [{'id': 'sign_in', 'code': 'sign_in', 'label': 'Sign in', 'status': 'complete'}]
        with mock.patch('export.views.get_access_requirements', return_value=complete), \
                self.assertLogs('export.views', level='WARNING') as logs:
            response = self.client.get(self.url())
        self.assertEqual(response.json()['reason'], 'other')
        self.assertIn('project=access-test', logs.output[0])

    @override_settings(
        MIDDLEWARE=settings.MIDDLEWARE + ['oauth2_provider.middleware.OAuth2TokenMiddleware'],
        AUTHENTICATION_BACKENDS=settings.AUTHENTICATION_BACKENDS + ['oauth2_provider.backends.OAuth2Backend'],
    )
    def test_user_set_by_token_middleware_is_not_session_authenticated(self):
        """A user attached by middleware without a session login is treated as anonymous."""
        app = Application.objects.create(
            name='Middleware test client', user=self.user, client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        )
        AccessToken.objects.create(
            user=self.user, application=app, token='middleware-test-token',
            scope='profile:read', expires=timezone.now() + timedelta(hours=1),
        )
        self.client.credentials(HTTP_AUTHORIZATION='Bearer middleware-test-token')
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['authenticated'])
        self.assertEqual(self.requirements(response)['credentialing']['status'], 'unknown')

    def test_contributor_review_uses_active_request(self):
        self.project.access_policy = AccessPolicy.CONTRIBUTOR_REVIEW
        self.project.required_trainings.clear()
        self.project.save(update_fields=['access_policy'])
        self.user.is_credentialed = True
        self.user.save(update_fields=['is_credentialed'])
        self.client.force_authenticate(self.user)
        request = DataAccessRequest.objects.create(
            project=self.project, requester=self.user, status=DataAccessRequest.PENDING_VALUE,
        )
        self.assertEqual(self.requirements(self.client.get(self.url()))['review']['status'], 'pending')
        request.status = DataAccessRequest.ACCEPT_REQUEST_VALUE
        request.decision_datetime = timezone.now()
        request.save(update_fields=['status', 'decision_datetime'])
        response = self.client.get(self.url())
        self.assertEqual(response.json()['status'], 'ready')
        self.assertEqual(self.requirements(response)['review']['status'], 'complete')

    def test_missing_version_is_404_and_bad_credentials_are_401(self):
        self.assertEqual(self.client.get(self.url('missing')).status_code, 404)
        token = base64.b64encode(b'accesstest:wrong').decode('ascii')
        self.client.credentials(HTTP_AUTHORIZATION=f'Basic {token}')
        self.assertEqual(self.client.get(self.url()).status_code, 401)

    def oauth_token(self, token, scope, application=None, expires_in=timedelta(hours=1)):
        """An OAuth access token for self.user, from a third-party application unless one is given."""
        if application is None:
            application = Application.objects.create(
                name='Third-party client', user=self.user, client_type=Application.CLIENT_CONFIDENTIAL,
                authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            )
        AccessToken.objects.create(
            user=self.user, application=application, token=token, scope=scope,
            expires=timezone.now() + expires_in,
        )
        return token

    def get_with_bearer(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return self.client.get(self.url())

    def assert_account_status(self, response):
        """The response describes self.user's own access, not an anonymous visitor's."""
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(response.json()['status'], 'action_required')
        self.assertEqual(self.requirements(response)['credentialing']['status'], 'required')

    def assert_anonymous_status(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['authenticated'])
        self.assertEqual(self.requirements(response)['credentialing']['status'], 'unknown')

    def test_personal_access_token_reads_its_own_account_status(self):
        """The user created the token for themselves, so any scope may read their own status."""
        _, token = PersonalAccessToken.create_for_user(self.user, [DOWNLOAD_TOKEN_SCOPE])
        self.assert_account_status(self.get_with_bearer(token))

    def test_personal_token_cannot_select_another_account(self):
        other = User.objects.create_user(
            email='other-access-test@example.com', username='otheruser',
            password='other-password', is_active=True,
        )
        other.is_credentialed = True
        other.save(update_fields=['is_credentialed'])
        _, token = PersonalAccessToken.create_for_user(self.user, [DOWNLOAD_TOKEN_SCOPE])
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        response = self.client.get(self.url(), {'username': other.username, 'user_id': other.pk})

        self.assert_account_status(response)

    def test_invalid_or_expired_personal_access_token_is_401(self):
        record, token = PersonalAccessToken.create_for_user(self.user, [DOWNLOAD_TOKEN_SCOPE])
        record.expires = timezone.now() - timedelta(seconds=1)
        record.save(update_fields=['expires'])
        self.assertEqual(self.get_with_bearer(token).status_code, 401)
        self.assertEqual(self.get_with_bearer(PersonalAccessToken.PREFIX + 'not-a-real-token').status_code, 401)

    def test_personal_access_token_of_an_inactive_account_is_401(self):
        _, token = PersonalAccessToken.create_for_user(self.user, [DOWNLOAD_TOKEN_SCOPE])
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertEqual(self.get_with_bearer(token).status_code, 401)

    def test_python_package_sign_in_reads_its_own_account_status(self):
        """Tokens from PhysioNet's own applications need no extra scope."""
        python_client = Application.objects.get(client_id=PYTHON_CLIENT_ID)
        token = self.oauth_token('python-client-token', 'data:download profile:read', application=python_client)
        self.assert_account_status(self.get_with_bearer(token))

    def test_third_party_token_with_credentialing_read_reads_account_status(self):
        token = self.oauth_token('third-party-credentialing', 'profile:read credentialing:read')
        self.assert_account_status(self.get_with_bearer(token))

    def test_third_party_token_without_credentialing_read_is_anonymous(self):
        """The user did not let this application read their credentialing or training status."""
        for scope in ('profile:read', 'data:download', 'profile:read data:download'):
            with self.subTest(scope=scope):
                token = self.oauth_token(f'third-party-{scope}', scope)
                self.assert_anonymous_status(self.get_with_bearer(token))

    def test_invalid_or_expired_oauth_token_is_401(self):
        python_client = Application.objects.get(client_id=PYTHON_CLIENT_ID)
        expired = self.oauth_token('expired-python-client-token', 'data:download', application=python_client,
                                   expires_in=-timedelta(seconds=1))
        self.assertEqual(self.get_with_bearer(expired).status_code, 401)
        self.assertEqual(self.get_with_bearer('not-a-real-token').status_code, 401)

    def test_session_login_is_authenticated(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url())
        self.assertTrue(response.json()['authenticated'])
        self.assertEqual(self.requirements(response)['credentialing']['status'], 'required')

    def test_each_required_training_has_its_own_id(self):
        second = TrainingType.objects.create(name='Second Access Training')
        self.project.required_trainings.add(second)
        Training.objects.create(
            slug='second-training', user=self.user, training_type=second,
            status=TrainingStatus.ACCEPTED, process_datetime=timezone.now(),
        )
        self.client.force_authenticate(self.user)
        trainings = {
            item['id']: item for item in self.client.get(self.url()).json()['requirements']
            if item['code'] == 'training'
        }
        self.assertEqual(trainings, {
            f'training:{self.training.pk}': {
                'id': f'training:{self.training.pk}', 'code': 'training', 'label': self.training.name,
                'status': 'required', 'url': 'http://testserver' + reverse('edit_training'),
            },
            f'training:{second.pk}': {
                'id': f'training:{second.pk}', 'code': 'training', 'label': second.name,
                'status': 'complete', 'url': 'http://testserver' + reverse('edit_training'),
            },
        })

    @override_settings(BLOCKED_REGIONS={'XX'})
    def test_blocked_region_is_reported_before_requirements(self):
        self.project.georestricted = True
        self.project.save(update_fields=['georestricted'])
        self.client.force_authenticate(self.user)
        with mock.patch('project.authorization.access.get_country_code', return_value='XX'):
            response = self.client.get(self.url())
        self.assertFalse(response.json()['can_download'])
        self.assertEqual(response.json()['status'], 'unavailable')
        self.assertEqual(response.json()['reason'], 'region_blocked')

    def test_requirements_agree_with_access_decision(self):
        """All steps complete exactly when can_access_project allows access."""
        second = TrainingType.objects.create(name='Second Access Training')
        self.project.required_trainings.add(second)
        policies = [AccessPolicy.RESTRICTED, AccessPolicy.CREDENTIALED, AccessPolicy.CONTRIBUTOR_REVIEW]
        # 'renewed' has two valid copies of one type and none of the second.
        training_sets = {
            0: [], 1: [self.training], 2: [self.training, second],
            'renewed': [self.training, self.training],
        }
        for policy, credentialed, trainings, dua, approved in itertools.product(
            policies, (False, True), tuple(training_sets), (False, True), (False, True)
        ):
            with self.subTest(policy=policy, credentialed=credentialed, trainings=trainings,
                              dua=dua, approved=approved):
                self.project.access_policy = policy
                self.project.save(update_fields=['access_policy'])
                self.user.is_credentialed = credentialed
                self.user.save(update_fields=['is_credentialed'])
                Training.objects.filter(user=self.user).delete()
                for index, training_type in enumerate(training_sets[trainings]):
                    Training.objects.create(
                        slug=f'agree-{index}', user=self.user, training_type=training_type,
                        status=TrainingStatus.ACCEPTED, process_datetime=timezone.now(),
                    )
                DUASignature.objects.filter(user=self.user).delete()
                if dua:
                    DUASignature.objects.create(project=self.project, user=self.user)
                DataAccessRequest.objects.filter(requester=self.user).delete()
                if approved:
                    DataAccessRequest.objects.create(
                        project=self.project, requester=self.user,
                        status=DataAccessRequest.ACCEPT_REQUEST_VALUE, decision_datetime=timezone.now(),
                    )
                all_complete = all(
                    item['status'] == 'complete'
                    for item in get_access_requirements(self.project, self.user)
                )
                self.assertEqual(all_complete, can_access_project(self.project, self.user))
