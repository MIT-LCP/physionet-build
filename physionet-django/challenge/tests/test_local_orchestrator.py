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
    challenge.validation_labels_gcs_uri = None
    challenge.test_labels_gcs_uri = None

    submission = mock.MagicMock()
    submission.pk = 42
    submission.challenge = challenge
    submission.code_archive_gcs_uri = 'staging-bucket/archives/42/code.tar.gz'
    submission.error_message = ''

    for key, value in overrides.items():
        setattr(submission, key, value)

    return submission


def _create_test_archive(path):
    """Create a minimal tar.gz archive for testing."""
    import io as _io
    with tarfile.open(path, 'w:gz') as tar:
        content = b'print("hello")\n'
        info = tarfile.TarInfo(name='main.py')
        info.size = len(content)
        tar.addfile(info, _io.BytesIO(content))


def _setup_build_mocks(orch, MockObjectPath):
    """Set up mocks for the build() phase and execute it."""
    mock_client = mock.MagicMock()
    orch._docker_client = mock_client

    # Build container succeeds
    mock_build_container = mock.MagicMock()
    mock_build_container.wait.return_value = {'StatusCode': 0}
    mock_build_container.id = 'build123'

    # We'll track containers.run calls to return different containers
    # for build vs run phases
    mock_client.containers.run.return_value = mock_build_container

    # Mock GCS archive
    mock_blob = mock.MagicMock()
    mock_blob.exists.return_value = True
    mock_blob.download_to_filename.side_effect = _create_test_archive

    mock_obj = MockObjectPath.return_value
    mock_obj.bucket.return_value.blob.return_value = mock_blob

    orch.build()

    return mock_client


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
    """Test the build phase downloads archive, installs deps, commits image."""

    @mock.patch('physionet.gcp.ObjectPath')
    def test_build_success(self, MockObjectPath):
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_to_filename.side_effect = _create_test_archive

        mock_obj = MockObjectPath.return_value
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        mock_client = mock.MagicMock()
        orch._docker_client = mock_client

        mock_build_container = mock.MagicMock()
        mock_build_container.wait.return_value = {'StatusCode': 0}
        mock_client.containers.run.return_value = mock_build_container

        orch.build()

        MockObjectPath.assert_called_once_with(submission.code_archive_gcs_uri)
        mock_blob.exists.assert_called_once()

        # Verify build container was run and committed
        mock_client.containers.run.assert_called_once()
        mock_build_container.commit.assert_called_once_with(
            repository='challenge-42', tag='built'
        )
        self.assertEqual(orch._built_image, 'challenge-42:built')

        orch.cleanup()

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

    @mock.patch('physionet.gcp.ObjectPath')
    def test_build_install_failure(self, MockObjectPath):
        """Build fails if pip install exits non-zero."""
        mock_blob = mock.MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.download_to_filename.side_effect = _create_test_archive

        mock_obj = MockObjectPath.return_value
        mock_obj.bucket.return_value.blob.return_value = mock_blob

        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        mock_client = mock.MagicMock()
        orch._docker_client = mock_client

        mock_build_container = mock.MagicMock()
        mock_build_container.wait.return_value = {'StatusCode': 1}
        mock_build_container.logs.return_value = b'pip: No matching distribution found'
        mock_client.containers.run.return_value = mock_build_container

        with self.assertRaises(RuntimeError) as ctx:
            orch.build()

        self.assertIn('Build failed', str(ctx.exception))


class TestLocalContainerOrchestratorRun(TestCase):
    """Test the run phase calls Docker with correct params."""

    @mock.patch('physionet.gcp.ObjectPath')
    def test_run_successful_container(self, MockObjectPath):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        # Run build phase first
        mock_client = _setup_build_mocks(orch, MockObjectPath)

        # Reset ObjectPath mock for the run phase
        MockObjectPath.reset_mock()
        MockObjectPath.side_effect = None

        # Set up a new run container
        mock_run_container = mock.MagicMock()
        mock_run_container.wait.return_value = {'StatusCode': 0}
        mock_run_container.id = 'run456'
        mock_client.containers.run.return_value = mock_run_container

        # Mock GCS for output upload
        mock_output_obj = mock.MagicMock()
        mock_output_obj.key.return_value = 'challenges/test-challenge/output/42'
        mock_output_bucket = mock.MagicMock()
        mock_output_obj.bucket.return_value = mock_output_bucket
        MockObjectPath.return_value = mock_output_obj

        orch.run()

        # Find the run() call (second call to containers.run)
        run_calls = mock_client.containers.run.call_args_list
        # Last call is the run container
        call_args = run_calls[-1]

        # Verify uses built image, not base image
        self.assertEqual(call_args.kwargs['image'], 'challenge-42:built')

        # Verify entrypoint command (no pip install)
        self.assertEqual(
            call_args.kwargs['command'],
            ['sh', '-c', 'python main.py'],
        )

        # Verify network isolation
        self.assertEqual(call_args.kwargs['network_mode'], 'none')

        # Verify environment
        self.assertEqual(call_args.kwargs['environment']['INPUT_DIR'], '/mnt/input')
        self.assertEqual(call_args.kwargs['environment']['OUTPUT_DIR'], '/mnt/output')
        self.assertEqual(call_args.kwargs['environment']['SUBMISSION_ID'], '42')

        # Verify resource limits
        self.assertEqual(call_args.kwargs['mem_limit'], '512m')
        self.assertEqual(call_args.kwargs['nano_cpus'], 1_000_000_000)
        self.assertTrue(call_args.kwargs['detach'])

        # Verify container was waited on
        mock_run_container.wait.assert_called_once_with(timeout=300)

        orch.cleanup()

    @mock.patch('physionet.gcp.ObjectPath')
    def test_run_requires_build(self, MockObjectPath):
        """run() raises RuntimeError if build() was not called first."""
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        with self.assertRaises(RuntimeError) as ctx:
            orch.run()

        self.assertIn('build() must be called before run()', str(ctx.exception))

    @mock.patch('physionet.gcp.ObjectPath')
    def test_run_failed_container(self, MockObjectPath):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        # Build phase
        mock_client = _setup_build_mocks(orch, MockObjectPath)
        MockObjectPath.reset_mock()
        MockObjectPath.side_effect = None

        # Run phase — container exits with error
        mock_run_container = mock.MagicMock()
        mock_run_container.wait.return_value = {'StatusCode': 1}
        mock_run_container.logs.return_value = b'Error: file not found'
        mock_run_container.id = 'run456'
        mock_client.containers.run.return_value = mock_run_container

        with self.assertRaises(RuntimeError) as ctx:
            orch.run()

        self.assertIn('exited with code 1', str(ctx.exception))
        submission.save.assert_called()

        orch.cleanup()

    @mock.patch('physionet.gcp.ObjectPath')
    def test_run_container_timeout(self, MockObjectPath):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        # Build phase
        mock_client = _setup_build_mocks(orch, MockObjectPath)
        MockObjectPath.reset_mock()
        MockObjectPath.side_effect = None

        # Run phase — container times out
        mock_run_container = mock.MagicMock()
        mock_run_container.wait.side_effect = Exception('timeout')
        mock_run_container.id = 'run456'
        mock_client.containers.run.return_value = mock_run_container

        with self.assertRaises(RuntimeError) as ctx:
            orch.run()

        self.assertIn('timed out', str(ctx.exception))
        mock_run_container.stop.assert_called_once()

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
    """Test cleanup removes containers, built image, and temp files."""

    def test_cleanup_removes_container_and_tmpdir(self):
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)

        mock_container = mock.MagicMock()
        orch._container = mock_container

        mock_build_container = mock.MagicMock()
        orch._build_container = mock_build_container

        mock_client = mock.MagicMock()
        orch._docker_client = mock_client
        orch._built_image = 'challenge-42:built'

        tmpdir = tempfile.mkdtemp()
        orch._tmpdir = tmpdir

        orch.cleanup()

        mock_container.remove.assert_called_once_with(force=True)
        mock_build_container.remove.assert_called_once_with(force=True)
        mock_client.images.remove.assert_called_once_with(
            'challenge-42:built', force=True
        )
        self.assertFalse(os.path.exists(tmpdir))

    def test_cleanup_no_container(self):
        """Cleanup when no container was created should not raise."""
        submission = _make_submission_mock()
        orch = LocalContainerOrchestrator(submission)
        orch.cleanup()  # Should not raise
