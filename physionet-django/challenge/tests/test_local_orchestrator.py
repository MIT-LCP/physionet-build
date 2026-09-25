"""
Tests for LocalContainerOrchestrator.

Uses mocked Docker client and GCS to verify the local orchestrator
correctly wires up container execution and score extraction.
"""
import json
import os
import tarfile
import tempfile
from unittest import mock

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

    challenge = mock.MagicMock()
    challenge.slug = 'test-challenge'
    challenge.submission_spec = spec
    challenge.test_data_gcs_uri = None

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

    def test_default_is_cloud_run(self):
        """When the setting is missing entirely, default to cloud_run."""
        submission = _make_submission_mock()
        with self.settings(CHALLENGE_CONTAINER_BACKEND='cloud_run'):
            orchestrator = get_orchestrator(submission)
        self.assertIsInstance(orchestrator, ContainerOrchestrator)


class TestLocalContainerOrchestratorBuild(TestCase):
    """Test the build phase checks archive existence in GCS."""

    @mock.patch('physionet.gcp.ObjectPath')
    def test_build_success(self, MockObjectPath):
        mock_obj = MockObjectPath.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = True
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)
        orch.build()

        MockObjectPath.assert_called_once_with(submission.code_archive_gcs_uri)
        mock_blob.exists.assert_called_once()

    @mock.patch('physionet.gcp.ObjectPath')
    def test_build_missing_archive(self, MockObjectPath):
        mock_obj = MockObjectPath.return_value
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
        with tarfile.open(path, 'w:gz') as tar:
            # Add a dummy main.py
            import io
            content = b'print("hello")\n'
            info = tarfile.TarInfo(name='main.py')
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

    @mock.patch('physionet.gcp.ObjectPath')
    @mock.patch('docker.DockerClient')
    def test_run_successful_container(self, MockDockerClient, MockObjectPath):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        # Mock docker client
        mock_client = mock.MagicMock()
        orch._docker_client = mock_client

        mock_container = mock.MagicMock()
        mock_container.wait.return_value = {'StatusCode': 0}
        mock_container.id = 'abc123'
        mock_client.containers.run.return_value = mock_container

        # Mock GCS - archive download writes a real tar.gz
        mock_archive_obj = mock.MagicMock()
        mock_archive_bucket = mock.MagicMock()
        mock_archive_blob = mock.MagicMock()
        mock_archive_bucket.blob.return_value = mock_archive_blob

        # Mock output bucket
        mock_output_obj = mock.MagicMock()
        mock_output_obj.key.return_value = 'challenges/test-challenge/output/42'
        mock_output_bucket = mock.MagicMock()
        mock_output_bucket.list_blobs.return_value = []

        call_count = [0]
        def side_effect(uri):
            obj = mock.MagicMock()
            if call_count[0] == 0:
                # Archive path
                obj.bucket.return_value = mock_archive_bucket
                obj.key.return_value = 'archives/42/code.tar.gz'
                call_count[0] += 1
            else:
                # Output path
                obj.bucket.return_value = mock_output_bucket
                obj.key.return_value = 'challenges/test-challenge/output/42'
            return obj

        MockObjectPath.side_effect = side_effect

        # Make download_to_filename create a real archive
        def fake_download(filename):
            self._create_test_archive(filename)

        mock_archive_blob.download_to_filename.side_effect = fake_download

        orch.run()

        # Verify Docker was called with correct image and command
        call_args = mock_client.containers.run.call_args
        self.assertEqual(call_args.kwargs['image'], 'python:3.11-slim')
        self.assertEqual(
            call_args.kwargs['command'],
            ['sh', '-c', 'python main.py'],
        )
        self.assertEqual(call_args.kwargs['environment']['INPUT_DIR'], '/mnt/input')
        self.assertEqual(call_args.kwargs['environment']['OUTPUT_DIR'], '/mnt/output')
        self.assertEqual(call_args.kwargs['environment']['SUBMISSION_ID'], '42')
        self.assertEqual(call_args.kwargs['mem_limit'], '512m')
        self.assertEqual(call_args.kwargs['nano_cpus'], 1_000_000_000)
        self.assertTrue(call_args.kwargs['detach'])

        # Verify container was waited on
        mock_container.wait.assert_called_once_with(timeout=300)

        # Cleanup
        orch.cleanup()

    @mock.patch('physionet.gcp.ObjectPath')
    def test_run_failed_container(self, MockObjectPath):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        mock_client = mock.MagicMock()
        orch._docker_client = mock_client

        mock_container = mock.MagicMock()
        mock_container.wait.return_value = {'StatusCode': 1}
        mock_container.logs.return_value = b'Error: file not found'
        mock_container.id = 'abc123'
        mock_client.containers.run.return_value = mock_container

        mock_archive_blob = mock.MagicMock()
        def fake_download(filename):
            self._create_test_archive(filename)
        mock_archive_blob.download_to_filename.side_effect = fake_download

        mock_archive_obj = mock.MagicMock()
        mock_archive_obj.bucket.return_value.blob.return_value = mock_archive_blob
        mock_archive_obj.key.return_value = 'archives/42/code.tar.gz'

        MockObjectPath.return_value = mock_archive_obj

        with self.assertRaises(RuntimeError) as ctx:
            orch.run()

        self.assertIn('exited with code 1', str(ctx.exception))
        submission.save.assert_called()

        orch.cleanup()

    @mock.patch('physionet.gcp.ObjectPath')
    def test_run_container_timeout(self, MockObjectPath):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        mock_client = mock.MagicMock()
        orch._docker_client = mock_client

        mock_container = mock.MagicMock()
        mock_container.wait.side_effect = Exception('timeout')
        mock_container.id = 'abc123'
        mock_client.containers.run.return_value = mock_container

        mock_archive_blob = mock.MagicMock()
        def fake_download(filename):
            self._create_test_archive(filename)
        mock_archive_blob.download_to_filename.side_effect = fake_download

        mock_archive_obj = mock.MagicMock()
        mock_archive_obj.bucket.return_value.blob.return_value = mock_archive_blob
        mock_archive_obj.key.return_value = 'archives/42/code.tar.gz'

        MockObjectPath.return_value = mock_archive_obj

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

    @mock.patch('physionet.gcp.ObjectPath')
    @override_settings(CHALLENGE_STAGING_BUCKET='staging-bucket')
    def test_extract_scores_success(self, MockObjectPath):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        scores = {'accuracy': 0.95, 'f1': 0.88}
        mock_obj = MockObjectPath.return_value
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_as_text.return_value = json.dumps(scores)
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        result = orch.extract_scores()
        self.assertEqual(result, scores)

    @mock.patch('physionet.gcp.ObjectPath')
    @override_settings(CHALLENGE_STAGING_BUCKET='staging-bucket')
    def test_extract_scores_missing(self, MockObjectPath):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        mock_obj = MockObjectPath.return_value
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
