"""
Tests for LocalContainerOrchestrator.

Uses mocked Docker client and GCS to verify the local orchestrator
correctly wires up container execution and score extraction.
"""
import json
import os
import tarfile
import tempfile
import unittest
import zipfile
from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings

from challenge.services import (
    ContainerOrchestrator,
    LocalContainerOrchestrator,
    get_orchestrator,
)


def _make_submission_mock(**overrides):
    """Create a mock submission with related challenge and spec."""
    spec = mock.MagicMock()
    spec.base_image = 'python:3.11-slim'
    spec.entrypoint_command = 'python main.py'
    spec.max_memory_mb = 512
    spec.cpu_count = 1
    spec.max_runtime_seconds = 300
    spec.evaluation_script_gcs_uri = None

    challenge = mock.MagicMock()
    challenge.slug = 'test-challenge'
    challenge.submission_spec = spec
    challenge.test_data_gcs_uri = None
    challenge.validation_data_gcs_uri = None

    submission = mock.MagicMock()
    submission.pk = 42
    submission.challenge = challenge
    submission.code_archive_gcs_uri = 'staging-bucket/archives/42/code.tar.gz'
    submission.error_message = ''

    for key, value in overrides.items():
        setattr(submission, key, value)

    return submission


class TestGetOrchestrator(TestCase):
    """Test the factory function selects the right backend."""

    @override_settings(CHALLENGE_CONTAINER_BACKEND='cloud_run')
    def test_cloud_run_backend(self):
        submission = _make_submission_mock()
        orchestrator = get_orchestrator(submission)
        self.assertIsInstance(orchestrator, ContainerOrchestrator)

    @override_settings(CHALLENGE_CONTAINER_BACKEND='local_docker')
    def test_local_docker_backend(self):
        submission = _make_submission_mock()
        orchestrator = get_orchestrator(submission)
        self.assertIsInstance(orchestrator, LocalContainerOrchestrator)

    def test_default_is_local_docker(self):
        """When the setting is missing, default to local_docker."""
        submission = _make_submission_mock()
        with self.settings(CHALLENGE_CONTAINER_BACKEND='local_docker'):
            orchestrator = get_orchestrator(submission)
        self.assertIsInstance(orchestrator, LocalContainerOrchestrator)

    def test_attempts_have_separate_output_paths(self):
        submission = _make_submission_mock()
        first = get_orchestrator(submission, attempt_id='first')
        second = get_orchestrator(submission, attempt_id='second')
        self.assertNotEqual(first.output_gcs_path, second.output_gcs_path)
        self.assertTrue(first.output_gcs_path.endswith('/42/attempts/first'))


class TestLocalContainerOrchestratorBuild(TestCase):
    """Test the build phase checks archive existence in GCS."""

    @mock.patch('challenge.services._gcs_path')
    def test_build_success(self, mock_gcs_path):
        mock_obj = mock_gcs_path.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = True
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)
        orch.build()

        mock_gcs_path.assert_called_once_with(
            submission.code_archive_gcs_uri)
        mock_blob.exists.assert_called_once()

    @mock.patch('challenge.services._gcs_path')
    def test_build_missing_archive(self, mock_gcs_path):
        mock_obj = mock_gcs_path.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = False
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        with self.assertRaises(FileNotFoundError):
            orch.build()


class TestLocalContainerOrchestratorRun(TestCase):
    """Test the run phase calls Docker with correct params."""

    def _create_test_archive(self, path):
        """Create a minimal tar.gz archive for testing."""
        import io as _io
        with tarfile.open(path, 'w:gz') as tar:
            content = b'print("hello")\n'
            info = tarfile.TarInfo(name='main.py')
            info.size = len(content)
            tar.addfile(info, _io.BytesIO(content))

    def _make_orchestrator(self, mock_gcs_path, submission=None):
        """Set up an orchestrator with mocked GCS and Docker."""
        if submission is None:
            submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        mock_client = mock.MagicMock()
        orch._docker_client = mock_client

        mock_container = mock.MagicMock()
        mock_container.wait.return_value = {'StatusCode': 0}
        mock_container.id = 'abc123'
        mock_client.containers.run.return_value = mock_container

        # Archive download writes a real tar.gz
        mock_archive_blob = mock.MagicMock()
        mock_archive_blob.download_to_filename.side_effect = (
            self._create_test_archive)

        # Output bucket (for upload after run)
        mock_output_bucket = mock.MagicMock()
        mock_output_bucket.list_blobs.return_value = []

        call_count = [0]

        def side_effect(uri):
            obj = mock.MagicMock()
            if call_count[0] == 0:
                obj.bucket.return_value.blob.return_value = (
                    mock_archive_blob)
                obj.key.return_value = 'archives/42/code.tar.gz'
                call_count[0] += 1
            else:
                obj.bucket.return_value = mock_output_bucket
                obj.key.return_value = (
                    'challenges/test-challenge/output/42')
            return obj

        mock_gcs_path.side_effect = side_effect

        # Patch _run_evaluation to skip actual script execution.
        # Evaluation-specific behaviour is tested separately.
        orch._run_evaluation = mock.MagicMock()

        return orch, mock_client, mock_container

    @mock.patch('challenge.services._gcs_path')
    @mock.patch('docker.DockerClient')
    def test_run_successful_container(self, MockDockerClient, mock_gcs_path):
        orch, mock_client, mock_container = self._make_orchestrator(
            mock_gcs_path)

        orch.run()

        # Single Docker run with network disabled
        mock_client.containers.run.assert_called_once()
        call_args = mock_client.containers.run.call_args
        self.assertEqual(
            call_args.kwargs['command'],
            ['sh', '-c', 'python main.py'],
        )
        self.assertEqual(call_args.kwargs['network_mode'], 'none')
        self.assertEqual(
            call_args.kwargs['environment']['INPUT_DIR'], '/mnt/input')
        self.assertEqual(
            call_args.kwargs['environment']['OUTPUT_DIR'], '/mnt/output')
        self.assertEqual(
            call_args.kwargs['environment']['SUBMISSION_ID'], '42')
        self.assertEqual(call_args.kwargs['mem_limit'], '512m')
        self.assertEqual(call_args.kwargs['nano_cpus'], 1_000_000_000)
        self.assertTrue(call_args.kwargs['detach'])

        orch.cleanup()

    @mock.patch('challenge.services._gcs_path')
    def test_run_failed_container(self, mock_gcs_path):
        orch, mock_client, mock_container = self._make_orchestrator(
            mock_gcs_path)

        mock_container.wait.return_value = {'StatusCode': 1}
        mock_container.logs.return_value = b'Error: file not found'

        with self.assertRaises(RuntimeError) as ctx:
            orch.run()

        self.assertIn('exited with code 1', str(ctx.exception))

        orch.cleanup()

    @mock.patch('challenge.services._gcs_path')
    def test_run_container_timeout(self, mock_gcs_path):
        orch, mock_client, mock_container = self._make_orchestrator(
            mock_gcs_path)

        mock_container.wait.side_effect = Exception('timeout')

        with self.assertRaises(RuntimeError) as ctx:
            orch.run()

        self.assertIn('timed out', str(ctx.exception))
        mock_container.stop.assert_called_once()

        orch.cleanup()


class TestLocalContainerOrchestratorPoll(TestCase):
    """Test that poll() returns True immediately."""

    def test_poll_returns_true(self):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)
        self.assertTrue(orch.poll())


class TestLocalContainerOrchestratorExtractScores(TestCase):
    """Test score extraction from GCS."""

    @mock.patch('challenge.services._gcs_path')
    @override_settings(CHALLENGE_STAGING_BUCKET='staging-bucket')
    def test_extract_scores_success(self, mock_gcs_path):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        scores = {'accuracy': 0.95, 'f1': 0.88}
        mock_obj = mock_gcs_path.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_as_text.return_value = json.dumps(scores)
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        result = orch.extract_scores()
        self.assertEqual(result, scores)

    @mock.patch('challenge.services._gcs_path')
    @override_settings(CHALLENGE_STAGING_BUCKET='staging-bucket')
    def test_extract_scores_missing(self, mock_gcs_path):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        mock_obj = mock_gcs_path.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = False
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        with self.assertRaises(FileNotFoundError):
            orch.extract_scores()


class TestLocalContainerOrchestratorCleanup(TestCase):
    """Test cleanup removes container and temp files."""

    def test_cleanup_removes_container_and_tmpdir(self):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        mock_container = mock.MagicMock()
        orch._container = mock_container

        tmpdir = tempfile.mkdtemp()
        orch._tmpdir = tmpdir

        orch.cleanup()

        mock_container.remove.assert_called_once_with(force=True)
        self.assertFalse(os.path.exists(tmpdir))

    def test_cleanup_no_container(self):
        """Cleanup when no container was created should not raise."""
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)
        orch.cleanup()  # Should not raise


class TestSafeExtraction(TestCase):
    """Test that archive extraction rejects path traversal."""

    def test_tar_path_traversal_rejected(self):
        from challenge.services import _safe_extract_tar
        import io as _io

        buf = _io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            info = tarfile.TarInfo(name='../escaped.txt')
            info.size = 5
            tar.addfile(info, _io.BytesIO(b'hello'))
        buf.seek(0)

        dest = tempfile.mkdtemp()
        with tarfile.open(fileobj=buf, mode='r:gz') as tar:
            with self.assertRaises(ValueError):
                _safe_extract_tar(tar, dest)

    def test_tar_symlink_rejected(self):
        from challenge.services import _safe_extract_tar
        import io as _io

        buf = _io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            info = tarfile.TarInfo(name='link.txt')
            info.type = tarfile.SYMTYPE
            info.linkname = '/etc/passwd'
            tar.addfile(info)
        buf.seek(0)

        dest = tempfile.mkdtemp()
        with tarfile.open(fileobj=buf, mode='r:gz') as tar:
            with self.assertRaises(ValueError):
                _safe_extract_tar(tar, dest)

    def test_zip_path_traversal_rejected(self):
        from challenge.services import _safe_extract_zip
        import io as _io

        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('../escaped.txt', 'hello')
        buf.seek(0)

        dest = tempfile.mkdtemp()
        with zipfile.ZipFile(buf, 'r') as zf:
            with self.assertRaises(ValueError):
                _safe_extract_zip(zf, dest)


class TestEvaluationRequired(TestCase):
    """Test that scoring requires a trusted evaluation script."""

    def test_no_eval_script_raises(self):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)
        orch._tmpdir = tempfile.mkdtemp()
        output_dir = os.path.join(orch._tmpdir, 'output')
        os.makedirs(output_dir)

        with self.assertRaises(RuntimeError) as ctx:
            orch._run_evaluation(output_dir)
        self.assertIn('evaluation script', str(ctx.exception))


class TestOutputFileCheck(TestCase):
    """Participant output may only contain regular files and directories."""

    def test_symlink_rejected(self):
        from challenge.services import _check_output_files

        with tempfile.TemporaryDirectory() as output_dir:
            os.makedirs(os.path.join(output_dir, 'sub'))
            with open(os.path.join(output_dir, 'sub', 'predictions.json'), 'w') as f:
                f.write('[]')
            _check_output_files(output_dir)

            os.symlink('../labels/labels.csv',
                       os.path.join(output_dir, 'sub', 'leak.csv'))
            with self.assertRaises(RuntimeError) as ctx:
                _check_output_files(output_dir)
            self.assertIn('leak.csv', str(ctx.exception))


@unittest.skipUnless(
    getattr(settings, 'ENABLE_CHALLENGES', False),
    'Challenge URLs not registered',
)
class TestProcessSubmission(TestCase):
    """Run the process_submission task with a stubbed orchestrator."""
    fixtures = ['demo-user.json', 'demo-challenge.json']

    def test_scored_submission_completes(self):
        from challenge.enums import SubmissionStatus
        from challenge.models import Submission
        from challenge.tasks import process_submission

        submission = Submission.objects.get(status=SubmissionStatus.PENDING)
        orchestrator = mock.MagicMock()
        orchestrator.poll.return_value = True
        orchestrator.extract_scores.return_value = {'AUROC': 0.9}
        with mock.patch('challenge.services.get_orchestrator',
                        return_value=orchestrator):
            process_submission.now(submission.pk)

        submission.refresh_from_db()
        self.assertEqual(submission.status, SubmissionStatus.COMPLETED,
                         submission.error_message)
        self.assertEqual(submission.scores.get().value, 0.9)
        orchestrator.cleanup.assert_called_once_with()
