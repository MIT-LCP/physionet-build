"""
Container orchestration service for challenge submissions.

Manages GCP Cloud Run Jobs lifecycle: build, run, extract scores, cleanup.
Provides a local Docker backend for development/testing.
"""
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import zipfile

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


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
    def executions_client(self):
        from google.cloud import run_v2
        return run_v2.ExecutionsClient()

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
        from physionet.gcp import ObjectPath

        archive_path = ObjectPath(self.submission.code_archive_gcs_uri)
        blob = archive_path.bucket().blob(archive_path.key())
        if not blob.exists():
            raise FileNotFoundError(
                f'Code archive not found: {self.submission.code_archive_gcs_uri}'
            )

        logger.info('Build verified for submission %s', self.submission.pk)

    def run(self):
        """Create and execute a Cloud Run Job."""
        from google.cloud import run_v2

        staging_bucket = getattr(settings, 'CHALLENGE_STAGING_BUCKET', '')
        hidden_bucket = getattr(settings, 'CHALLENGE_HIDDEN_DATA_BUCKET', '')

        env_vars = [
            run_v2.EnvVar(name='INPUT_DIR', value='/mnt/input'),
            run_v2.EnvVar(name='OUTPUT_DIR', value='/mnt/output'),
            run_v2.EnvVar(name='SUBMISSION_ID', value=str(self.submission.pk)),
        ]

        container = run_v2.Container(
            image=self.spec.base_image,
            command=['sh', '-c'],
            args=[self.spec.entrypoint_command],
            env=env_vars,
            resources=run_v2.ResourceRequirements(
                limits={
                    'memory': f'{self.spec.max_memory_mb}Mi',
                    'cpu': str(self.spec.cpu_count),
                },
            ),
        )

        task_template = run_v2.TaskTemplate(
            containers=[container],
            timeout=f'{self.spec.max_runtime_seconds}s',
            max_retries=0,
        )

        job = run_v2.Job(
            template=run_v2.ExecutionTemplate(
                task_count=1,
                template=task_template,
            ),
        )

        # Create the job
        operation = self.client.create_job(
            parent=self.parent,
            job=job,
            job_id=self.job_name,
        )
        created_job = operation.result()

        self.submission.cloud_run_job_name = created_job.name
        self.submission.started_datetime = timezone.now()
        self.submission.save(update_fields=[
            'cloud_run_job_name', 'started_datetime',
        ])

        # Execute the job
        execution_operation = self.client.run_job(name=created_job.name)
        execution = execution_operation.result()
        self.submission.cloud_run_execution_name = execution.name
        self.submission.save(update_fields=['cloud_run_execution_name'])

        logger.info('Job executed for submission %s: %s',
                     self.submission.pk, execution.name)

    def poll(self, poll_interval=10, max_polls=360):
        """
        Poll for job completion. Returns True if completed successfully.
        """
        from google.cloud import run_v2

        execution_name = self.submission.cloud_run_execution_name
        if not execution_name:
            raise ValueError('No execution name set on submission')

        for _ in range(max_polls):
            execution = self.executions_client.get_execution(
                name=execution_name,
            )
            if execution.reconciling:
                time.sleep(poll_interval)
                continue

            if execution.succeeded_count > 0:
                return True

            if execution.failed_count > 0:
                self.submission.error_message = (
                    'Container execution failed. '
                    'Check logs for details.'
                )
                self.submission.save(update_fields=['error_message'])
                return False

            time.sleep(poll_interval)

        # Timed out waiting
        self.submission.error_message = 'Timed out waiting for job completion.'
        self.submission.save(update_fields=['error_message'])
        return False

    def extract_scores(self):
        """Read scores.json from the output GCS path and return parsed metrics."""
        from physionet.gcp import ObjectPath

        scores_uri = f'{self.output_gcs_path}/scores.json'
        scores_path = ObjectPath(scores_uri)
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
        """Delete the Cloud Run Job after execution."""
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
        from physionet.gcp import ObjectPath

        archive_path = ObjectPath(self.submission.code_archive_gcs_uri)
        blob = archive_path.bucket().blob(archive_path.key())
        if not blob.exists():
            raise FileNotFoundError(
                f'Code archive not found: {self.submission.code_archive_gcs_uri}'
            )

        logger.info('Build verified for submission %s (local docker)', self.submission.pk)

    def run(self):
        """Run the submission container locally using Docker."""
        from physionet.gcp import ObjectPath

        self._tmpdir = tempfile.mkdtemp(prefix='challenge_')
        code_dir = os.path.join(self._tmpdir, 'code')
        input_dir = os.path.join(self._tmpdir, 'input')
        output_dir = os.path.join(self._tmpdir, 'output')
        os.makedirs(code_dir)
        os.makedirs(input_dir)
        os.makedirs(output_dir)

        # Download and extract code archive from GCS
        archive_obj = ObjectPath(self.submission.code_archive_gcs_uri)
        archive_blob = archive_obj.bucket().blob(archive_obj.key())
        archive_local = os.path.join(self._tmpdir, 'archive')
        archive_blob.download_to_filename(archive_local)

        if zipfile.is_zipfile(archive_local):
            with zipfile.ZipFile(archive_local, 'r') as zf:
                zf.extractall(path=code_dir)
        else:
            with tarfile.open(archive_local, 'r:*') as tar:
                tar.extractall(path=code_dir)

        # Download test data from GCS if available
        test_data_uri = getattr(self.challenge, 'test_data_gcs_uri', None)
        if test_data_uri:
            # Strip gs:// prefix if present — ObjectPath expects bucket/key
            if test_data_uri.startswith('gs://'):
                test_data_uri = test_data_uri[5:]
            try:
                test_data_obj = ObjectPath(test_data_uri)
                test_bucket = test_data_obj.bucket()
                prefix = test_data_obj.key()
                for blob in test_bucket.list_blobs(prefix=prefix):
                    rel_path = blob.name[len(prefix):].lstrip('/')
                    if not rel_path:
                        continue
                    local_path = os.path.join(input_dir, rel_path)
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    blob.download_to_filename(local_path)
            except Exception:
                logger.warning(
                    'Could not download test data from %s — skipping',
                    test_data_uri,
                )

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

        # Run container synchronously
        self._container = self.docker_client.containers.run(
            image=self.spec.base_image,
            command=['sh', '-c', self.spec.entrypoint_command],
            environment=environment,
            volumes=volumes,
            working_dir='/workspace',
            mem_limit=mem_limit,
            nano_cpus=nano_cpus,
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

        # Run the evaluation script to score predictions against labels
        self._run_evaluation(output_dir)

        # Upload output files to GCS
        output_obj = ObjectPath(self.output_gcs_path)
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
        then run the script to compare submission predictions against labels.

        The evaluation script is invoked as:
            python evaluate.py <predictions_dir> <labels_dir> <scores_output>

        It must write a JSON dict of {metric_name: value} to scores_output.
        """
        from physionet.gcp import ObjectPath

        eval_uri = self.spec.evaluation_script_gcs_uri
        if not eval_uri:
            logger.info(
                'No evaluation script configured — expecting container '
                'to write scores.json directly (submission %s)',
                self.submission.pk,
            )
            return

        # Download the evaluation script
        eval_obj = ObjectPath(eval_uri)
        eval_blob = eval_obj.bucket().blob(eval_obj.key())
        if not eval_blob.exists():
            raise FileNotFoundError(
                f'Evaluation script not found at {eval_uri}'
            )
        eval_dir = os.path.join(self._tmpdir, 'evaluation')
        os.makedirs(eval_dir, exist_ok=True)
        eval_script = os.path.join(eval_dir, 'evaluate.py')
        eval_blob.download_to_filename(eval_script)

        # Download ground-truth labels (validation data)
        labels_dir = os.path.join(self._tmpdir, 'labels')
        os.makedirs(labels_dir, exist_ok=True)
        val_uri = getattr(self.challenge, 'validation_data_gcs_uri', '')
        if val_uri:
            if val_uri.startswith('gs://'):
                val_uri = val_uri[5:]
            try:
                val_obj = ObjectPath(val_uri)
                val_bucket = val_obj.bucket()
                prefix = val_obj.key()
                for blob in val_bucket.list_blobs(prefix=prefix):
                    rel_path = blob.name[len(prefix):].lstrip('/')
                    if not rel_path:
                        continue
                    local_path = os.path.join(labels_dir, rel_path)
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    blob.download_to_filename(local_path)
            except Exception:
                logger.warning(
                    'Could not download validation data from %s', val_uri,
                )

        # Run: python evaluate.py <predictions_dir> <labels_dir> <scores_output>
        scores_output = os.path.join(output_dir, 'scores.json')
        result = subprocess.run(
            ['python', eval_script, output_dir, labels_dir, scores_output],
            capture_output=True, text=True,
            timeout=120,
        )
        if result.returncode != 0:
            error_msg = (
                f'Evaluation script failed (exit {result.returncode}):\n'
                f'{result.stderr}'
            )
            raise RuntimeError(error_msg[:2000])

        logger.info('Evaluation complete for submission %s', self.submission.pk)

    def poll(self):
        """Return True immediately — execution is synchronous in run()."""
        return True

    def extract_scores(self):
        """Read scores.json from the output GCS path and return parsed metrics."""
        from physionet.gcp import ObjectPath

        scores_uri = f'{self.output_gcs_path}/scores.json'
        scores_path = ObjectPath(scores_uri)
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


def get_orchestrator(submission):
    """Factory function to select the appropriate container orchestrator."""
    backend = getattr(settings, 'CHALLENGE_CONTAINER_BACKEND', 'cloud_run')
    if backend == 'local_docker':
        return LocalContainerOrchestrator(submission)
    return ContainerOrchestrator(submission)
