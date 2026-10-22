"""
Container orchestration service for challenge submissions.

Manages GCP Cloud Run Jobs lifecycle: build, run, extract scores, cleanup.
Provides a local Docker backend for development/testing.
"""
import json
import logging
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _gcs_path(uri):
    """Build an ObjectPath that uses the challenge storage client."""
    from physionet.gcp import ObjectPath, get_challenge_storage_client
    return ObjectPath(uri, client=get_challenge_storage_client())


class ContainerOrchestrator:
    """
    Manages the lifecycle of a Cloud Run Job for a challenge submission.

    Workflow:
        1. build()  - Verify code archive, prepare staging area
        2. run()    - Create and execute Cloud Run Job
        3. poll()   - Wait for job completion
        4. extract_scores() - Read scores.json from output
        5. cleanup() - Delete Cloud Run Job
    """

    def __init__(self, submission):
        self.submission = submission
        self.challenge = submission.challenge
        self.spec = self.challenge.submission_spec
        self.project_id = getattr(settings, 'CHALLENGE_GCP_PROJECT_ID', '')
        self.region = getattr(settings, 'CHALLENGE_GCP_REGION', 'us-central1')
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google.cloud import run_v2
            self._client = run_v2.JobsClient()
        return self._client

    @property
    def job_name(self):
        return f'challenge-{self.challenge.slug}-sub-{self.submission.pk}'

    @property
    def parent(self):
        return f'projects/{self.project_id}/locations/{self.region}'

    @property
    def full_job_name(self):
        return f'{self.parent}/jobs/{self.job_name}'

    @property
    def output_gcs_path(self):
        bucket = getattr(settings, 'CHALLENGE_STAGING_BUCKET', '')
        return f'{bucket}/challenges/{self.challenge.slug}/output/{self.submission.pk}'

    def build(self):
        """Verify the code archive exists in GCS and prepare staging."""
        if not self.submission.code_archive_gcs_uri:
            raise FileNotFoundError(
                f'No code archive URI set for submission {self.submission.pk}'
            )

        archive_path = _gcs_path(self.submission.code_archive_gcs_uri)
        blob = archive_path.bucket().blob(archive_path.key())
        if not blob.exists():
            raise FileNotFoundError(
                f'Code archive not found: {self.submission.code_archive_gcs_uri}'
            )

        logger.info('Build verified for submission %s', self.submission.pk)

    def run(self):
        raise NotImplementedError(
            'Cloud Run backend does not yet stage code, input data, '
            'or run evaluation. Use CHALLENGE_CONTAINER_BACKEND='
            'local_docker until the Cloud Run pipeline is complete.'
        )

    def poll(self, poll_interval=10, max_polls=360):
        raise NotImplementedError

    def extract_scores(self):
        raise NotImplementedError

    def cleanup(self):
        """Delete the Cloud Run Job after execution."""
        if not self.submission.cloud_run_job_name:
            return
        try:
            self.client.delete_job(name=self.full_job_name)
            logger.info('Cleaned up job %s', self.full_job_name)
        except Exception:
            logger.exception('Failed to cleanup job %s', self.full_job_name)


class LocalContainerOrchestrator:
    """
    Local Docker-based orchestrator for development and testing.

    Replaces Cloud Run with local Docker execution via docker-py,
    allowing the full submission pipeline to run with docker-compose.
    """

    def __init__(self, submission):
        self.submission = submission
        self.challenge = submission.challenge
        self.spec = self.challenge.submission_spec
        self._docker_client = None
        self._container = None
        self._tmpdir = None

    @property
    def docker_client(self):
        if self._docker_client is None:
            import docker
            self._docker_client = docker.from_env()
        return self._docker_client

    @property
    def output_gcs_path(self):
        bucket = getattr(settings, 'CHALLENGE_STAGING_BUCKET', '')
        return f'{bucket}/challenges/{self.challenge.slug}/output/{self.submission.pk}'

    def build(self):
        """Verify the code archive exists in GCS."""
        if not self.submission.code_archive_gcs_uri:
            raise FileNotFoundError(
                f'No code archive URI set for submission {self.submission.pk}'
            )

        archive_path = _gcs_path(self.submission.code_archive_gcs_uri)
        blob = archive_path.bucket().blob(archive_path.key())
        if not blob.exists():
            raise FileNotFoundError(
                f'Code archive not found: {self.submission.code_archive_gcs_uri}'
            )

        logger.info('Build verified for submission %s (local docker)', self.submission.pk)

    def run(self):
        """Run the submission container locally using Docker."""
        self._tmpdir = tempfile.mkdtemp(prefix='challenge_')
        code_dir = os.path.join(self._tmpdir, 'code')
        input_dir = os.path.join(self._tmpdir, 'input')
        output_dir = os.path.join(self._tmpdir, 'output')
        os.makedirs(code_dir)
        os.makedirs(input_dir)
        os.makedirs(output_dir)

        # Download and extract code archive from GCS
        archive_obj = _gcs_path(self.submission.code_archive_gcs_uri)
        archive_blob = archive_obj.bucket().blob(archive_obj.key())
        archive_local = os.path.join(self._tmpdir, 'archive')
        archive_blob.download_to_filename(archive_local)

        if zipfile.is_zipfile(archive_local):
            with zipfile.ZipFile(archive_local, 'r') as zf:
                _safe_extract_zip(zf, code_dir)
        else:
            with tarfile.open(archive_local, 'r:*') as tar:
                _safe_extract_tar(tar, code_dir)

        # Download input data (features only, no labels) for participant
        # code. Labels stay in validation_data_gcs_uri for the evaluator.
        input_data_uri = getattr(
            self.challenge, 'test_data_gcs_uri', None)
        if input_data_uri:
            if input_data_uri.startswith('gs://'):
                input_data_uri = input_data_uri[5:]
            _download_gcs_data(_gcs_path(input_data_uri), input_dir)

        # Build container config
        mem_limit = f'{self.spec.max_memory_mb}m'
        nano_cpus = int(self.spec.cpu_count * 1e9)
        environment = {
            'INPUT_DIR': '/mnt/input',
            'OUTPUT_DIR': '/mnt/output',
            'SUBMISSION_ID': str(self.submission.pk),
        }
        volumes = {
            code_dir: {'bind': '/workspace', 'mode': 'ro'},
            input_dir: {'bind': '/mnt/input', 'mode': 'ro'},
            output_dir: {'bind': '/mnt/output', 'mode': 'rw'},
        }

        self.submission.started_datetime = timezone.now()
        self.submission.save(update_fields=['started_datetime'])

        # Run submission code with network disabled.  The base image
        # must include all required packages — we do not run pip from
        # participant-supplied requirements.txt because package install
        # hooks can execute arbitrary code with network access.
        self._container = self.docker_client.containers.run(
            image=self.spec.base_image,
            command=['sh', '-c', self.spec.entrypoint_command],
            environment=environment,
            volumes=volumes,
            working_dir='/workspace',
            mem_limit=mem_limit,
            nano_cpus=nano_cpus,
            network_mode='none',
            detach=True,
        )

        # Wait for completion with timeout
        try:
            result = self._container.wait(timeout=self.spec.max_runtime_seconds)
        except Exception:
            self._container.stop()
            self.submission.error_message = (
                f'Container timed out after {self.spec.max_runtime_seconds}s.'
            )
            self.submission.save(update_fields=['error_message'])
            raise RuntimeError(self.submission.error_message)

        exit_code = result.get('StatusCode', -1)
        if exit_code != 0:
            logs = self._container.logs(tail=50).decode('utf-8', errors='replace')
            error_msg = f'Container exited with code {exit_code}.\n{logs}'
            self.submission.error_message = error_msg[:2000]
            self.submission.save(update_fields=['error_message'])
            raise RuntimeError(error_msg[:2000])

        # Participant code controls the output directory. Reject links
        # and special files before the worker copies or uploads anything.
        _check_output_files(output_dir)

        # Run the evaluation script to score predictions against labels
        self._run_evaluation(output_dir)

        # Upload output files to GCS
        output_obj = _gcs_path(self.output_gcs_path)
        output_bucket = output_obj.bucket()
        for root, _dirs, files in os.walk(output_dir):
            for fname in files:
                local_file = os.path.join(root, fname)
                rel_path = os.path.relpath(local_file, output_dir)
                gcs_key = f'{output_obj.key()}/{rel_path}'
                blob = output_bucket.blob(gcs_key)
                blob.upload_from_filename(local_file)

        logger.info('Local container completed for submission %s', self.submission.pk)

    def _run_evaluation(self, output_dir):
        """
        Download the evaluation script and ground-truth labels from GCS,
        then run the evaluator in an isolated container.

        The container is invoked as:
            python /eval/evaluate.py /predictions /labels /output/scores.json

        It must write a JSON dict of {metric_name: value} to the output.
        """
        eval_uri = self.spec.evaluation_script_gcs_uri
        if not eval_uri:
            raise RuntimeError(
                'No evaluation script configured. Submissions cannot '
                'be scored without a trusted evaluation script.'
            )

        # Download the evaluation script
        eval_dir = os.path.join(self._tmpdir, 'evaluation')
        os.makedirs(eval_dir, exist_ok=True)
        eval_obj = _gcs_path(eval_uri)
        eval_blob = eval_obj.bucket().blob(eval_obj.key())
        if not eval_blob.exists():
            raise FileNotFoundError(
                f'Evaluation script not found at {eval_uri}'
            )
        eval_blob.download_to_filename(
            os.path.join(eval_dir, 'evaluate.py'))

        # Download ground-truth labels (only the evaluator sees these)
        labels_dir = os.path.join(self._tmpdir, 'labels')
        os.makedirs(labels_dir, exist_ok=True)
        val_uri = getattr(self.challenge, 'validation_data_gcs_uri', '')
        if val_uri:
            if val_uri.startswith('gs://'):
                val_uri = val_uri[5:]
            _download_gcs_data(_gcs_path(val_uri), labels_dir)

        # Copy predictions so the evaluator gets a read-only snapshot
        # while writing scores.json to the real output directory.
        predictions_dir = os.path.join(self._tmpdir, 'predictions')
        shutil.copytree(output_dir, predictions_dir)

        # Run evaluation in a container with no network.
        eval_container = self.docker_client.containers.run(
            image=self.spec.base_image,
            command=[
                'python', '/eval/evaluate.py',
                '/predictions', '/labels', '/output/scores.json',
            ],
            volumes={
                eval_dir: {'bind': '/eval', 'mode': 'ro'},
                predictions_dir: {'bind': '/predictions', 'mode': 'ro'},
                labels_dir: {'bind': '/labels', 'mode': 'ro'},
                output_dir: {'bind': '/output', 'mode': 'rw'},
            },
            network_mode='none',
            detach=True,
        )
        try:
            result = eval_container.wait(timeout=120)
            exit_code = result.get('StatusCode', -1)
            if exit_code != 0:
                logs = eval_container.logs(tail=50).decode(
                    'utf-8', errors='replace')
                raise RuntimeError(
                    (f'Evaluation script failed (exit {exit_code}):'
                     f'\n{logs}')[:2000])
        finally:
            eval_container.remove(force=True)

        logger.info(
            'Evaluation complete for submission %s', self.submission.pk)

    def poll(self):
        """Return True immediately — execution is synchronous in run()."""
        return True

    def extract_scores(self):
        """Read scores.json from the output GCS path and return parsed metrics."""
        scores_uri = f'{self.output_gcs_path}/scores.json'
        scores_path = _gcs_path(scores_uri)
        blob = scores_path.bucket().blob(scores_path.key())

        if not blob.exists():
            raise FileNotFoundError(
                f'scores.json not found at {scores_uri}'
            )

        raw = blob.download_as_text()
        scores = json.loads(raw)
        logger.info('Extracted scores for submission %s: %s',
                    self.submission.pk, scores)
        return scores

    def cleanup(self):
        """Remove the Docker container and temp directories."""
        if self._container:
            try:
                self._container.remove(force=True)
                logger.info('Removed container %s', self._container.id)
            except Exception:
                logger.exception('Failed to remove container')
        if self._tmpdir and os.path.exists(self._tmpdir):
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            logger.info('Cleaned up temp dir %s', self._tmpdir)


def _download_gcs_data(obj_path, dest_dir):
    """Download GCS data into dest_dir.

    Tries three strategies in order:
    1. Prefix listing — if multiple blobs exist under the key, download
       them preserving directory structure (handles seeded demo data).
    2. Single blob archive — download and extract zip/tar.
    3. Single blob file — copy as-is.
    """
    os.makedirs(dest_dir, exist_ok=True)
    bucket = obj_path.bucket()
    prefix = obj_path.key()
    if not prefix.endswith('/'):
        prefix_with_slash = prefix + '/'
    else:
        prefix_with_slash = prefix

    # Try prefix listing first
    blobs = list(bucket.list_blobs(prefix=prefix_with_slash, max_results=1))
    if blobs:
        for blob in bucket.list_blobs(prefix=prefix_with_slash):
            rel_path = blob.name[len(prefix_with_slash):]
            if not rel_path:
                continue
            local_path = os.path.join(dest_dir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            blob.download_to_filename(local_path)
        return

    # Fall back to single blob (archive or plain file)
    blob = bucket.blob(obj_path.key())
    if not blob.exists():
        logger.warning('GCS path not found: %s', obj_path.key())
        return

    tmp_dir = tempfile.mkdtemp()
    try:
        local_file = os.path.join(
            tmp_dir, os.path.basename(obj_path.key()))
        blob.download_to_filename(local_file)

        if zipfile.is_zipfile(local_file):
            with zipfile.ZipFile(local_file, 'r') as zf:
                _safe_extract_zip(zf, dest_dir)
        elif tarfile.is_tarfile(local_file):
            with tarfile.open(local_file, 'r:*') as tar:
                _safe_extract_tar(tar, dest_dir)
        else:
            shutil.copy2(local_file, dest_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _check_output_files(output_dir):
    """Reject anything in output_dir that is not a regular file or directory.

    Symlinks would otherwise be followed on the worker when the output is
    copied for the evaluator and uploaded to GCS.
    """
    for root, dirs, files in os.walk(output_dir):
        for name in dirs + files:
            path = os.path.join(root, name)
            mode = os.lstat(path).st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise RuntimeError(
                    'Output must contain only regular files and directories: '
                    f'{os.path.relpath(path, output_dir)}'
                )


def _safe_extract_tar(tar, dest):
    """Extract a tar archive, rejecting members that escape dest."""
    dest = os.path.realpath(dest)
    for member in tar.getmembers():
        member_path = os.path.realpath(os.path.join(dest, member.name))
        if not member_path.startswith(dest + os.sep) and member_path != dest:
            raise ValueError(
                f'Tar member escapes extraction directory: {member.name}'
            )
        if member.issym() or member.islnk():
            raise ValueError(
                f'Tar member is a link: {member.name}'
            )
    tar.extractall(path=dest)


def _safe_extract_zip(zf, dest):
    """Extract a zip archive, rejecting members that escape dest."""
    dest = os.path.realpath(dest)
    for info in zf.infolist():
        member_path = os.path.realpath(os.path.join(dest, info.filename))
        if not member_path.startswith(dest + os.sep) and member_path != dest:
            raise ValueError(
                f'Zip member escapes extraction directory: {info.filename}'
            )
    zf.extractall(path=dest)


def get_orchestrator(submission):
    """Factory function to select the appropriate container orchestrator."""
    backend = getattr(
        settings, 'CHALLENGE_CONTAINER_BACKEND', 'local_docker')
    if backend == 'cloud_run':
        return ContainerOrchestrator(submission)
    return LocalContainerOrchestrator(submission)
