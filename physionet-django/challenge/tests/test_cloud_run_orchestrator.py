"""
Tests for ContainerOrchestrator (Cloud Run backend).

Uses mocked Cloud Run and GCS clients to verify the orchestrator
correctly creates jobs, polls execution status, and extracts scores.
"""
import json
import sys
from unittest import mock

from django.test import TestCase, override_settings

from challenge.enums import DatasetType
from challenge.services import ContainerOrchestrator, get_orchestrator

# Mock run_v2 so tests work without google-cloud-run installed.
_mock_run_v2 = mock.MagicMock()
_mock_run_v2.ExecutionEnvironment.EXECUTION_ENVIRONMENT_GEN2 = 2
_mock_run_v2.LaunchStage.GA = 1
_mock_run_v2.VpcAccess.VpcEgress.ALL_TRAFFIC = 1


def _install_mock_run_v2():
    sys.modules['google.cloud.run_v2'] = _mock_run_v2
    return _mock_run_v2


def _uninstall_mock_run_v2():
    sys.modules.pop('google.cloud.run_v2', None)


def _make_submission_mock(**overrides):
    spec = mock.MagicMock()
    spec.base_image = 'python:3.11-slim'
    spec.entrypoint_command = 'python main.py'
    spec.max_memory_mb = 512
    spec.cpu_count = 1
    spec.max_runtime_seconds = 300
    spec.evaluation_script_gcs_uri = (
        'challenge-submissions/eval/evaluate.py')
    spec.gpu_enabled = False
    spec.gpu_type = ''

    challenge = mock.MagicMock()
    challenge.slug = 'test-challenge'
    challenge.submission_spec = spec
    challenge.test_data_gcs_uri = (
        'challenge-submissions/data/test')
    challenge.validation_data_gcs_uri = (
        'challenge-submissions/data/val')
    challenge.test_labels_gcs_uri = (
        'challenge-submissions/labels/test')
    challenge.validation_labels_gcs_uri = (
        'challenge-submissions/labels/val')

    submission = mock.MagicMock()
    submission.pk = 42
    submission.challenge = challenge
    submission.code_archive_gcs_uri = (
        'challenge-submissions/archives/42/code.tar.gz')
    submission.error_message = ''
    submission.cloud_run_job_name = ''
    submission.cloud_run_execution_name = ''
    submission.started_datetime = None
    submission.test_scoring_error_message = ''

    for key, value in overrides.items():
        setattr(submission, key, value)

    return submission


_CLOUD_RUN_SETTINGS = {
    'CHALLENGE_CONTAINER_BACKEND': 'cloud_run',
    'CHALLENGE_GCP_PROJECT_ID': 'test-project',
    'CHALLENGE_GCP_REGION': 'us-central1',
    'CHALLENGE_STAGING_BUCKET': 'challenge-submissions',
    'CHALLENGE_EVAL_BUCKET': 'challenge-evaluation',
    'CHALLENGE_SUBMISSION_SA_EMAIL': (
        'sub-runner@test.iam.gserviceaccount.com'),
    'CHALLENGE_EVAL_SA_EMAIL': (
        'eval-runner@test.iam.gserviceaccount.com'),
    'CHALLENGE_VPC_CONNECTOR': (
        'projects/test-project/locations/us-central1'
        '/connectors/challenge-vpc-conn'
    ),
}


@override_settings(**_CLOUD_RUN_SETTINGS)
class TestCloudRunOrchestratorRun(TestCase):

    def setUp(self):
        self.mock_run_v2 = _install_mock_run_v2()

    def tearDown(self):
        _uninstall_mock_run_v2()

    def _make_orchestrator(self, submission=None):
        if submission is None:
            submission = _make_submission_mock()
        orch = ContainerOrchestrator(submission)

        mock_jobs_client = mock.MagicMock()
        orch._client = mock_jobs_client

        mock_execution = mock.MagicMock()
        mock_execution.failed_count = 0
        mock_execution.succeeded_count = 1

        mock_op = mock.MagicMock()
        mock_op.result.return_value = mock_execution
        mock_op.metadata.name = (
            'projects/test-project/locations/us-central1'
            '/jobs/challenge-test-challenge-sub-42'
            '/executions/exec-abc123'
        )
        mock_jobs_client.run_job.return_value = mock_op
        create_op = mock.MagicMock()
        create_op.result.return_value = mock.MagicMock()
        mock_jobs_client.create_job.return_value = create_op

        return orch, mock_jobs_client, mock_op

    @mock.patch('challenge.services._gcs_path')
    def test_run_creates_submission_and_eval_jobs(
        self, mock_gcs_path,
    ):
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        orch, mock_client, _ = self._make_orchestrator()
        orch.run()

        self.assertEqual(mock_client.create_job.call_count, 2)
        self.assertEqual(mock_client.run_job.call_count, 2)

        first_create = mock_client.create_job.call_args_list[0]
        self.assertIn(
            'sub-42', first_create.kwargs['job_id'])

        second_create = mock_client.create_job.call_args_list[1]
        self.assertIn(
            'eval-42', second_create.kwargs['job_id'])

    @mock.patch('challenge.services._gcs_path')
    def test_run_saves_job_name_and_execution(
        self, mock_gcs_path,
    ):
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        submission = _make_submission_mock()
        orch, _, _ = self._make_orchestrator(submission)
        orch.run()

        submission.save.assert_called()
        self.assertIn('sub-42', submission.cloud_run_job_name)
        self.assertIn(
            'exec-abc123',
            submission.cloud_run_execution_name,
        )

    @mock.patch('challenge.services._gcs_path')
    def test_run_sets_started_datetime(self, mock_gcs_path):
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        submission = _make_submission_mock()
        orch, _, _ = self._make_orchestrator(submission)
        orch.run()

        self.assertIsNotNone(submission.started_datetime)

    @mock.patch('challenge.services._gcs_path')
    def test_run_fails_when_submission_job_fails(
        self, mock_gcs_path,
    ):
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        submission = _make_submission_mock()
        orch, mock_client, _ = self._make_orchestrator(submission)

        failed_execution = mock.MagicMock()
        failed_execution.failed_count = 1
        failed_op = mock.MagicMock()
        failed_op.result.return_value = failed_execution
        failed_op.metadata.name = (
            'projects/p/locations/r/jobs/j/executions/e')
        mock_client.run_job.return_value = failed_op

        with self.assertRaises(RuntimeError) as ctx:
            orch.run()
        self.assertIn('exited with errors', str(ctx.exception))

    @mock.patch('challenge.services._gcs_path')
    def test_run_fails_without_sa_config(self, mock_gcs_path):
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        orch, _, _ = self._make_orchestrator()
        with self.settings(CHALLENGE_SUBMISSION_SA_EMAIL=''):
            with self.assertRaises(RuntimeError) as ctx:
                orch.run()
            self.assertIn(
                'must be configured', str(ctx.exception))

    @mock.patch('challenge.services._gcs_path')
    def test_run_fails_without_eval_script(self, mock_gcs_path):
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        submission = _make_submission_mock()
        submission.challenge.submission_spec \
            .evaluation_script_gcs_uri = ''
        orch, _, _ = self._make_orchestrator(submission)

        with self.assertRaises(RuntimeError) as ctx:
            orch.run()
        self.assertIn('evaluation script', str(ctx.exception))

    @mock.patch('challenge.services._gcs_path')
    def test_run_saves_error_to_test_scoring_field(
        self, mock_gcs_path,
    ):
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        submission = _make_submission_mock()
        orch, mock_client, _ = self._make_orchestrator(submission)

        failed_execution = mock.MagicMock()
        failed_execution.failed_count = 1
        failed_op = mock.MagicMock()
        failed_op.result.return_value = failed_execution
        failed_op.metadata.name = (
            'projects/p/locations/r/jobs/j/executions/e')
        mock_client.run_job.return_value = failed_op

        with self.assertRaises(RuntimeError):
            orch.run(dataset=DatasetType.TEST)

        self.assertIn(
            'exited with errors',
            submission.test_scoring_error_message,
        )

    @mock.patch('challenge.services._gcs_path')
    def test_run_without_gpu(self, mock_gcs_path):
        """When gpu_enabled=False, no GPU resource is requested."""
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        submission = _make_submission_mock()
        submission.challenge.submission_spec.gpu_enabled = False
        orch, _, _ = self._make_orchestrator(submission)
        with mock.patch.object(
            orch, '_create_and_run_job',
            wraps=orch._create_and_run_job,
        ) as spy:
            orch.run()

        sub_call = spy.call_args_list[0]
        self.assertIsNone(sub_call.kwargs.get('gpu_type'))

    @mock.patch('challenge.services._gcs_path')
    def test_run_with_gpu(self, mock_gcs_path):
        """When gpu_enabled=True, the GPU resource is requested."""
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        submission = _make_submission_mock()
        submission.challenge.submission_spec.gpu_enabled = True
        submission.challenge.submission_spec.gpu_type = 'nvidia-l4'
        orch, _, _ = self._make_orchestrator(submission)
        with mock.patch.object(
            orch, '_create_and_run_job',
            wraps=orch._create_and_run_job,
        ) as spy:
            orch.run()

        sub_call = spy.call_args_list[0]
        self.assertEqual(
            sub_call.kwargs.get('gpu_type'), 'nvidia-l4')

    @mock.patch('challenge.services._gcs_path')
    def test_gpu_not_passed_to_eval_job(self, mock_gcs_path):
        """Evaluation job never gets GPU even when submission does."""
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        submission = _make_submission_mock()
        submission.challenge.submission_spec.gpu_enabled = True
        submission.challenge.submission_spec.gpu_type = 'nvidia-l4'
        orch, _, _ = self._make_orchestrator(submission)
        with mock.patch.object(
            orch, '_create_and_run_job',
            wraps=orch._create_and_run_job,
        ) as spy:
            orch.run()

        eval_call = spy.call_args_list[1]
        self.assertIsNone(eval_call.kwargs.get('gpu_type'))

    @mock.patch('challenge.services._gcs_path')
    def test_eval_writes_to_eval_bucket(self, mock_gcs_path):
        """Eval output mount uses CHALLENGE_EVAL_BUCKET, not the
        submissions bucket."""
        mock_obj = mock.MagicMock()
        mock_obj.bucket.return_value.name = 'challenge-submissions'
        mock_obj.key.return_value = 'archives/42/code.tar.gz'
        mock_gcs_path.return_value = mock_obj

        orch, _, _ = self._make_orchestrator()
        with mock.patch.object(
            orch, '_create_and_run_job',
            wraps=orch._create_and_run_job,
        ) as spy:
            orch.run()

        eval_call = spy.call_args_list[1]
        eval_mounts = eval_call.kwargs['gcs_mounts']
        output_mount = [
            m for m in eval_mounts if m[0] == '/mnt/output'][0]
        self.assertEqual(output_mount[1], 'challenge-evaluation')

    @mock.patch('challenge.services._gcs_path')
    def test_scores_prefix_uses_eval_bucket(self, mock_gcs_path):
        """_scores_gcs_prefix references CHALLENGE_EVAL_BUCKET."""
        submission = _make_submission_mock()
        orch = ContainerOrchestrator(submission)
        self.assertTrue(
            orch._scores_gcs_prefix.startswith(
                'challenge-evaluation/'))

    def test_create_job_includes_gpu_in_resource_limits(self):
        """_create_and_run_job sets nvidia.com/gpu in limits."""
        self.mock_run_v2.reset_mock()
        submission = _make_submission_mock()
        orch, mock_client, _ = self._make_orchestrator(submission)

        orch._create_and_run_job(
            job_name='test-job',
            full_job_name=orch.full_job_name,
            service_account='sa@test.iam.gserviceaccount.com',
            entrypoint='echo ok',
            env_vars={},
            gcs_mounts=[],
            max_runtime_seconds=60,
            gpu_type='nvidia-l4',
        )

        # Check the limits dict passed to ResourceRequirements.
        rr_call = self.mock_run_v2.ResourceRequirements
        limits = rr_call.call_args.kwargs['limits']
        self.assertEqual(limits['nvidia.com/gpu'], '1')
        self.assertIn('cpu', limits)
        self.mock_run_v2.NodeSelector.assert_called_once_with(
            accelerator='nvidia-l4')

    def test_create_job_omits_gpu_when_none(self):
        """_create_and_run_job omits nvidia.com/gpu by default."""
        self.mock_run_v2.reset_mock()
        submission = _make_submission_mock()
        orch, mock_client, _ = self._make_orchestrator(submission)

        orch._create_and_run_job(
            job_name='test-job',
            full_job_name=orch.full_job_name,
            service_account='sa@test.iam.gserviceaccount.com',
            entrypoint='echo ok',
            env_vars={},
            gcs_mounts=[],
            max_runtime_seconds=60,
        )

        rr_call = self.mock_run_v2.ResourceRequirements
        limits = rr_call.call_args.kwargs['limits']
        self.assertNotIn('nvidia.com/gpu', limits)


@override_settings(**_CLOUD_RUN_SETTINGS)
class TestCloudRunOrchestratorPoll(TestCase):

    def setUp(self):
        self.mock_run_v2 = _install_mock_run_v2()

    def tearDown(self):
        _uninstall_mock_run_v2()

    def test_poll_returns_true_when_no_execution(self):
        submission = _make_submission_mock()
        submission.cloud_run_execution_name = ''
        orch = ContainerOrchestrator(submission)
        self.assertTrue(orch.poll())

    def test_poll_returns_true_on_success(self):
        submission = _make_submission_mock()
        submission.cloud_run_execution_name = (
            'projects/p/locations/r/jobs/j/executions/e')
        orch = ContainerOrchestrator(submission)

        mock_exec_client = mock.MagicMock()
        mock_execution = mock.MagicMock()
        mock_execution.reconciling = False
        mock_execution.failed_count = 0
        mock_exec_client.get_execution.return_value = (
            mock_execution)

        with mock.patch.object(
            type(orch), 'executions_client',
            new_callable=mock.PropertyMock,
            return_value=mock_exec_client,
        ):
            self.assertTrue(orch.poll())

    def test_poll_returns_false_when_reconciling(self):
        submission = _make_submission_mock()
        submission.cloud_run_execution_name = (
            'projects/p/locations/r/jobs/j/executions/e')
        orch = ContainerOrchestrator(submission)

        mock_exec_client = mock.MagicMock()
        mock_execution = mock.MagicMock()
        mock_execution.reconciling = True
        mock_exec_client.get_execution.return_value = (
            mock_execution)

        with mock.patch.object(
            type(orch), 'executions_client',
            new_callable=mock.PropertyMock,
            return_value=mock_exec_client,
        ):
            self.assertFalse(orch.poll())

    def test_poll_returns_false_on_failure(self):
        submission = _make_submission_mock()
        submission.cloud_run_execution_name = (
            'projects/p/locations/r/jobs/j/executions/e')
        orch = ContainerOrchestrator(submission)

        mock_exec_client = mock.MagicMock()
        mock_execution = mock.MagicMock()
        mock_execution.reconciling = False
        mock_execution.failed_count = 1
        mock_exec_client.get_execution.return_value = (
            mock_execution)

        with mock.patch.object(
            type(orch), 'executions_client',
            new_callable=mock.PropertyMock,
            return_value=mock_exec_client,
        ):
            self.assertFalse(orch.poll())

    def test_poll_returns_false_when_not_found(self):
        from google.api_core import exceptions as gapi_exceptions

        submission = _make_submission_mock()
        submission.cloud_run_execution_name = (
            'projects/p/locations/r/jobs/j/executions/e')
        orch = ContainerOrchestrator(submission)

        mock_exec_client = mock.MagicMock()
        mock_exec_client.get_execution.side_effect = (
            gapi_exceptions.NotFound('not found'))

        with mock.patch.object(
            type(orch), 'executions_client',
            new_callable=mock.PropertyMock,
            return_value=mock_exec_client,
        ):
            self.assertFalse(orch.poll())


@override_settings(**_CLOUD_RUN_SETTINGS)
class TestCloudRunOrchestratorExtractScores(TestCase):

    @mock.patch('challenge.services._gcs_path')
    def test_extract_scores_success(self, mock_gcs_path):
        submission = _make_submission_mock()
        orch = ContainerOrchestrator(submission)

        scores = {'accuracy': 0.95, 'f1': 0.88}
        mock_obj = mock_gcs_path.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_as_text.return_value = (
            json.dumps(scores))
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        result = orch.extract_scores()
        self.assertEqual(result, scores)

    @mock.patch('challenge.services._gcs_path')
    def test_extract_scores_missing(self, mock_gcs_path):
        submission = _make_submission_mock()
        orch = ContainerOrchestrator(submission)

        mock_obj = mock_gcs_path.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = False
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        with self.assertRaises(FileNotFoundError):
            orch.extract_scores()


@override_settings(**_CLOUD_RUN_SETTINGS)
class TestCloudRunOrchestratorCleanup(TestCase):

    def test_cleanup_deletes_both_jobs(self):
        submission = _make_submission_mock()
        submission.cloud_run_job_name = (
            'challenge-test-challenge-sub-42')
        orch = ContainerOrchestrator(submission)

        mock_client = mock.MagicMock()
        orch._client = mock_client

        orch.cleanup()

        self.assertEqual(mock_client.delete_job.call_count, 2)
        deleted = [
            c.kwargs['name']
            for c in mock_client.delete_job.call_args_list
        ]
        self.assertIn(orch.full_job_name, deleted)
        self.assertIn(orch.full_eval_job_name, deleted)

    def test_cleanup_ignores_not_found(self):
        from google.api_core import exceptions as gapi_exceptions

        submission = _make_submission_mock()
        orch = ContainerOrchestrator(submission)
        mock_client = mock.MagicMock()
        mock_client.delete_job.side_effect = (
            gapi_exceptions.NotFound('not found'))
        orch._client = mock_client

        orch.cleanup()


@override_settings(**_CLOUD_RUN_SETTINGS)
class TestCloudRunOrchestratorBuild(TestCase):

    @mock.patch('challenge.services._gcs_path')
    def test_build_success(self, mock_gcs_path):
        mock_obj = mock_gcs_path.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = True
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        submission = _make_submission_mock()
        orch = ContainerOrchestrator(submission)
        orch.build()

    @mock.patch('challenge.services._gcs_path')
    def test_build_missing_archive(self, mock_gcs_path):
        mock_obj = mock_gcs_path.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = False
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        submission = _make_submission_mock()
        orch = ContainerOrchestrator(submission)

        with self.assertRaises(FileNotFoundError):
            orch.build()

    def test_build_no_archive_uri(self):
        submission = _make_submission_mock(
            code_archive_gcs_uri='')
        orch = ContainerOrchestrator(submission)

        with self.assertRaises(FileNotFoundError):
            orch.build()


@override_settings(**_CLOUD_RUN_SETTINGS)
class TestCloudRunGetOrchestrator(TestCase):

    def test_returns_container_orchestrator(self):
        submission = _make_submission_mock()
        orch = get_orchestrator(submission)
        self.assertIsInstance(orch, ContainerOrchestrator)

    def test_attempt_id_in_output_path(self):
        submission = _make_submission_mock()
        orch = get_orchestrator(
            submission, attempt_id='abc123')
        self.assertIn('abc123', orch.output_gcs_path)

    def test_separate_output_paths(self):
        submission = _make_submission_mock()
        first = get_orchestrator(
            submission, attempt_id='first')
        second = get_orchestrator(
            submission, attempt_id='second')
        self.assertNotEqual(
            first.output_gcs_path, second.output_gcs_path)
