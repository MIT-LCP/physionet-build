"""
Container orchestration service for challenge submissions.

Manages GCP Cloud Run Jobs lifecycle: build, run, extract scores, cleanup.
"""
import json
import logging
import time

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
