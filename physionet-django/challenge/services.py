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

    # TODO: Network egress for Cloud Run Jobs should be restricted via
    # VPC connector / VPC Service Controls in the GCP project configuration.
    # This is infrastructure config (Terraform/gcloud), not application code.
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

        if not self.submission.code_archive_gcs_uri:
            raise FileNotFoundError(
                f'No code archive URI set for submission {self.submission.pk}'
            )

        archive_path = ObjectPath(self.submission.code_archive_gcs_uri)
        blob = archive_path.bucket().blob(archive_path.key())
        if not blob.exists():
            raise FileNotFoundError(
                f'Code archive not found: {self.submission.code_archive_gcs_uri}'
            )

        logger.info('Build verified for submission %s', self.submission.pk)

    def run(self, dataset=None):
        """Create and execute a Cloud Run Job."""
        from challenge.enums import DatasetType
        from google.cloud import run_v2

        if dataset is None:
            dataset = DatasetType.VAL

        staging_bucket = getattr(settings, 'CHALLENGE_STAGING_BUCKET', '')
        hidden_bucket = getattr(settings, 'CHALLENGE_HIDDEN_DATA_BUCKET', '')

        env_vars = [
            run_v2.EnvVar(name='INPUT_DIR', value='/mnt/input'),
            run_v2.EnvVar(name='OUTPUT_DIR', value='/mnt/output'),
            run_v2.EnvVar(name='SUBMISSION_ID', value=str(self.submission.pk)),
            run_v2.EnvVar(name='DATASET', value=str(dataset)),
        ]

        container = run_v2.Container(
            image=self.spec.base_image,
            command=['sh', '-c'],
            args=[
                f'if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi && {self.spec.entrypoint_command}'
            ],
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
        self._build_container = None
        self._built_image = None
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
        """
        Download the code archive, extract it, and run a build container
        WITH network access to install dependencies. The resulting container
        is committed as a local image for use in the network-isolated run().
        """
        from physionet.gcp import ObjectPath

        if not self.submission.code_archive_gcs_uri:
            raise FileNotFoundError(
                f'No code archive URI set for submission {self.submission.pk}'
            )

        archive_path = ObjectPath(self.submission.code_archive_gcs_uri)
        blob = archive_path.bucket().blob(archive_path.key())
        if not blob.exists():
            raise FileNotFoundError(
                f'Code archive not found: {self.submission.code_archive_gcs_uri}'
            )

        # Set up temp directories
        self._tmpdir = tempfile.mkdtemp(prefix='challenge_')
        code_dir = os.path.join(self._tmpdir, 'code')
        os.makedirs(code_dir)

        # Download and extract code archive
        archive_local = os.path.join(self._tmpdir, 'archive')
        blob.download_to_filename(archive_local)

        if zipfile.is_zipfile(archive_local):
            with zipfile.ZipFile(archive_local, 'r') as zf:
                zf.extractall(path=code_dir)
        else:
            with tarfile.open(archive_local, 'r:*') as tar:
                tar.extractall(path=code_dir)

        # Run a build container WITH network to install dependencies
        image_tag = f'challenge-{self.submission.pk}:built'
        volumes = {
            code_dir: {'bind': '/workspace', 'mode': 'ro'},
        }

        self._build_container = self.docker_client.containers.run(
            image=self.spec.base_image,
            command=[
                'sh', '-c',
                'cp -r /workspace/* /app/ && cd /app && '
                'if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi',
            ],
            volumes=volumes,
            working_dir='/app',
            detach=True,
        )

        result = self._build_container.wait(timeout=600)
        exit_code = result.get('StatusCode', -1)
        if exit_code != 0:
            logs = self._build_container.logs(tail=50).decode('utf-8', errors='replace')
            raise RuntimeError(
                f'Build failed (exit {exit_code}):\n{logs[:2000]}'
            )

        # Commit the stopped container as a new image
        self._build_container.commit(repository=f'challenge-{self.submission.pk}', tag='built')
        self._built_image = image_tag

        logger.info(
            'Build complete for submission %s — image %s (local docker)',
            self.submission.pk, image_tag,
        )

    def run(self, dataset=None):
        """
        Run the submission container locally using Docker.

        Uses the pre-built image from build() with network_mode='none'
        to prevent data exfiltration. Only mounts input data and output dir.
        """
        from challenge.enums import DatasetType
        from physionet.gcp import ObjectPath

        if dataset is None:
            dataset = DatasetType.VAL

        if not self._built_image:
            raise RuntimeError('build() must be called before run()')

        input_dir = os.path.join(self._tmpdir, 'input')
        output_dir = os.path.join(self._tmpdir, 'output')
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        # Download input data from GCS (records only, no labels)
        if dataset == DatasetType.TEST:
            data_uri = getattr(self.challenge, 'test_data_gcs_uri', '')
        else:
            data_uri = getattr(self.challenge, 'validation_data_gcs_uri', '')
        if data_uri:
            if data_uri.startswith('gs://'):
                data_uri = data_uri[5:]
            try:
                data_obj = ObjectPath(data_uri)
                data_bucket = data_obj.bucket()
                prefix = data_obj.key()
                for blob in data_bucket.list_blobs(prefix=prefix):
                    rel_path = blob.name[len(prefix):].lstrip('/')
                    if not rel_path:
                        continue
                    local_path = os.path.join(input_dir, rel_path)
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    blob.download_to_filename(local_path)
            except Exception:
                logger.warning(
                    'Could not download %s data from %s — skipping',
                    dataset, data_uri,
                )

        # Container config
        mem_limit = f'{self.spec.max_memory_mb}m'
        nano_cpus = int(self.spec.cpu_count * 1e9)
        environment = {
            'INPUT_DIR': '/mnt/input',
            'OUTPUT_DIR': '/mnt/output',
            'SUBMISSION_ID': str(self.submission.pk),
        }
        volumes = {
            input_dir: {'bind': '/mnt/input', 'mode': 'ro'},
            output_dir: {'bind': '/mnt/output', 'mode': 'rw'},
        }

        self.submission.started_datetime = timezone.now()
        self.submission.save(update_fields=['started_datetime'])

        # Run container from built image with NO network access
        self._container = self.docker_client.containers.run(
            image=self._built_image,
            command=['sh', '-c', self.spec.entrypoint_command],
            environment=environment,
            volumes=volumes,
            working_dir='/app',
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

        # Run the evaluation script to score predictions against labels
        self._run_evaluation(output_dir, dataset=dataset)

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

    def _run_evaluation(self, output_dir, dataset=None):
        """
        Download the evaluation script and ground-truth labels from GCS,
        then run the script to compare submission predictions against labels.

        The evaluation script is invoked as:
            python evaluate.py <predictions_dir> <labels_dir> <scores_output>

        It must write a JSON dict of {metric_name: value} to scores_output.

        When dataset is TEST, downloads labels from test_labels_gcs_uri instead
        of validation_labels_gcs_uri.
        """
        from challenge.enums import DatasetType
        from physionet.gcp import ObjectPath

        if dataset is None:
            dataset = DatasetType.VAL

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

        # Download ground-truth labels from dedicated label URIs
        # (separate from the input data to prevent label leakage)
        labels_dir = os.path.join(self._tmpdir, 'labels')
        os.makedirs(labels_dir, exist_ok=True)
        if dataset == DatasetType.TEST:
            labels_uri = getattr(self.challenge, 'test_labels_gcs_uri', '')
        else:
            labels_uri = getattr(self.challenge, 'validation_labels_gcs_uri', '')
        if labels_uri:
            if labels_uri.startswith('gs://'):
                labels_uri = labels_uri[5:]
            try:
                labels_obj = ObjectPath(labels_uri)
                labels_bucket = labels_obj.bucket()
                prefix = labels_obj.key()
                for blob in labels_bucket.list_blobs(prefix=prefix):
                    rel_path = blob.name[len(prefix):].lstrip('/')
                    if not rel_path:
                        continue
                    local_path = os.path.join(labels_dir, rel_path)
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    blob.download_to_filename(local_path)
            except Exception:
                logger.warning(
                    'Could not download %s data from %s', dataset, labels_uri,
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
        """Remove Docker containers, built image, and temp directories."""
        if self._container:
            try:
                self._container.remove(force=True)
                logger.info('Removed run container %s', self._container.id)
            except Exception:
                logger.exception('Failed to remove run container')
        if self._build_container:
            try:
                self._build_container.remove(force=True)
                logger.info('Removed build container %s', self._build_container.id)
            except Exception:
                logger.exception('Failed to remove build container')
        if self._built_image:
            try:
                self.docker_client.images.remove(self._built_image, force=True)
                logger.info('Removed built image %s', self._built_image)
            except Exception:
                logger.exception('Failed to remove built image %s', self._built_image)
        if self._tmpdir and os.path.exists(self._tmpdir):
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            logger.info('Cleaned up temp dir %s', self._tmpdir)


def get_orchestrator(submission):
    """Factory function to select the appropriate container orchestrator."""
    backend = getattr(settings, 'CHALLENGE_CONTAINER_BACKEND', 'cloud_run')
    if backend == 'local_docker':
        return LocalContainerOrchestrator(submission)
    return ContainerOrchestrator(submission)
