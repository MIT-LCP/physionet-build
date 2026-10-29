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

from challenge.enums import DatasetType

logger = logging.getLogger(__name__)


def _gcs_path(uri):
    """Build an ObjectPath that uses the challenge storage client."""
    from physionet.gcp import ObjectPath, get_challenge_storage_client
    return ObjectPath(uri, client=get_challenge_storage_client())


class ContainerOrchestrator:
    """
    Manages Cloud Run Jobs for challenge submissions.

    Two-phase execution:
        Phase 1 (submission): Runs untrusted participant code against
        input data with network restricted via VPC connector. Writes
        predictions to a GCS prefix via GCS FUSE.

        Phase 2 (evaluation): Runs the trusted evaluation script
        against predictions and ground-truth labels. Writes
        scores.json to GCS.

    Both phases use Gen2 execution environment for GCS FUSE and
    network policy enforcement. GPU is provisioned when the
    challenge's SubmissionSpec sets gpu_enabled=True.
    """

    def __init__(self, submission, attempt_id=None):
        self.submission = submission
        self.attempt_id = attempt_id
        self.challenge = submission.challenge
        self.spec = self.challenge.submission_spec
        self.project_id = getattr(
            settings, 'CHALLENGE_GCP_PROJECT_ID', '')
        self.region = getattr(
            settings, 'CHALLENGE_GCP_REGION', 'us-central1')
        self._client = None
        self._executions_client = None
        self._execution_name = None

    @property
    def client(self):
        if self._client is None:
            from google.cloud import run_v2
            self._client = run_v2.JobsClient()
        return self._client

    @property
    def executions_client(self):
        if self._executions_client is None:
            from google.cloud import run_v2
            self._executions_client = run_v2.ExecutionsClient()
        return self._executions_client

    @property
    def job_name(self):
        return (f'challenge-{self.challenge.slug}'
                f'-sub-{self.submission.pk}')

    @property
    def eval_job_name(self):
        return (f'challenge-{self.challenge.slug}'
                f'-eval-{self.submission.pk}')

    @property
    def parent(self):
        return f'projects/{self.project_id}/locations/{self.region}'

    @property
    def full_job_name(self):
        return f'{self.parent}/jobs/{self.job_name}'

    @property
    def full_eval_job_name(self):
        return f'{self.parent}/jobs/{self.eval_job_name}'

    @property
    def output_gcs_path(self):
        bucket = getattr(settings, 'CHALLENGE_STAGING_BUCKET', '')
        path = (f'{bucket}/challenges/{self.challenge.slug}'
                f'/output/{self.submission.pk}')
        if self.attempt_id:
            return f'{path}/attempts/{self.attempt_id}'
        return path

    @property
    def _predictions_gcs_prefix(self):
        return f'{self.output_gcs_path}/predictions'

    @property
    def _scores_gcs_prefix(self):
        eval_bucket = getattr(
            settings, 'CHALLENGE_EVAL_BUCKET', '')
        path = (f'{eval_bucket}/challenges/{self.challenge.slug}'
                f'/output/{self.submission.pk}')
        if self.attempt_id:
            return f'{path}/attempts/{self.attempt_id}/scores'
        return f'{path}/scores'

    def _save_submission_field(self, field, value):
        setattr(self.submission, field, value)
        if self.attempt_id:
            updated = type(self.submission).objects.filter(
                pk=self.submission.pk,
                test_scoring_claim_id=self.attempt_id,
                test_scoring_in_progress=True,
            ).update(**{field: value})
            return updated > 0
        else:
            self.submission.save(update_fields=[field])
            return True

    def _check_claim(self):
        if not self.attempt_id:
            return
        still_held = type(self.submission).objects.filter(
            pk=self.submission.pk,
            test_scoring_claim_id=self.attempt_id,
            test_scoring_in_progress=True,
        ).exists()
        if not still_held:
            raise RuntimeError(
                f'Claim {self.attempt_id} expired for '
                f'submission {self.submission.pk}')

    def _save_run_error(self, message, dataset):
        field = ('test_scoring_error_message'
                 if dataset == DatasetType.TEST
                 else 'error_message')
        self._save_submission_field(field, message)

    def build(self):
        """Verify the code archive exists in GCS."""
        if not self.submission.code_archive_gcs_uri:
            raise FileNotFoundError(
                f'No code archive URI set for submission '
                f'{self.submission.pk}'
            )

        archive_path = _gcs_path(
            self.submission.code_archive_gcs_uri)
        blob = archive_path.bucket().blob(archive_path.key())
        if not blob.exists():
            raise FileNotFoundError(
                f'Code archive not found: '
                f'{self.submission.code_archive_gcs_uri}'
            )

        logger.info(
            'Build verified for submission %s', self.submission.pk)

    def _create_and_run_job(self, job_name, full_job_name,
                            service_account, entrypoint, env_vars,
                            gcs_mounts, max_runtime_seconds,
                            vpc_access=None, gpu_type=None):
        """Create a Cloud Run Job and execute it."""
        from google.cloud import run_v2
        from google.api_core import exceptions as gapi_exceptions

        volumes = []
        volume_mounts = []
        for mount_path, bucket_name, mount_options in gcs_mounts:
            vol_name = mount_path.strip('/').replace('/', '-')
            volumes.append(run_v2.Volume(
                name=vol_name,
                gcs=run_v2.GCSVolumeSource(
                    bucket=bucket_name,
                    read_only='ro' in mount_options,
                ),
            ))
            volume_mounts.append(run_v2.VolumeMount(
                name=vol_name,
                mount_path=mount_path,
            ))

        resource_limits = {
            'cpu': str(self.spec.cpu_count),
            'memory': f'{self.spec.max_memory_mb}Mi',
        }
        if gpu_type:
            resource_limits['nvidia.com/gpu'] = '1'

        container = run_v2.Container(
            image=self.spec.base_image,
            command=['sh', '-c', entrypoint],
            env=[run_v2.EnvVar(name=k, value=v)
                 for k, v in env_vars.items()],
            resources=run_v2.ResourceRequirements(
                limits=resource_limits,
            ),
            volume_mounts=volume_mounts,
        )

        task_template = run_v2.TaskTemplate(
            containers=[container],
            volumes=volumes,
            max_retries=0,
            timeout=f'{max_runtime_seconds}s',
            service_account=service_account,
            execution_environment=(
                run_v2.ExecutionEnvironment
                .EXECUTION_ENVIRONMENT_GEN2
            ),
        )
        if vpc_access:
            task_template.vpc_access = vpc_access
        if gpu_type:
            task_template.node_selector = run_v2.NodeSelector(
                accelerator=gpu_type)

        job = run_v2.Job(
            template=run_v2.ExecutionTemplate(
                template=task_template,
            ),
        )

        try:
            self.client.delete_job(name=full_job_name).result()
        except gapi_exceptions.NotFound:
            pass

        operation = self.client.create_job(
            parent=self.parent,
            job=job,
            job_id=job_name,
        )
        operation.result()

        return self.client.run_job(name=full_job_name)

    def run(self, dataset=None):
        """Execute the two-phase Cloud Run pipeline."""
        from google.cloud import run_v2

        if dataset is None:
            dataset = DatasetType.VAL

        bucket = getattr(
            settings, 'CHALLENGE_STAGING_BUCKET', '')
        eval_bucket = getattr(
            settings, 'CHALLENGE_EVAL_BUCKET', '')
        submission_sa = getattr(
            settings, 'CHALLENGE_SUBMISSION_SA_EMAIL', '')
        eval_sa = getattr(
            settings, 'CHALLENGE_EVAL_SA_EMAIL', '')
        vpc_connector = getattr(
            settings, 'CHALLENGE_VPC_CONNECTOR', '')

        required = {
            'CHALLENGE_STAGING_BUCKET': bucket,
            'CHALLENGE_EVAL_BUCKET': eval_bucket,
            'CHALLENGE_SUBMISSION_SA_EMAIL': submission_sa,
            'CHALLENGE_EVAL_SA_EMAIL': eval_sa,
            'CHALLENGE_VPC_CONNECTOR': vpc_connector,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                f'{", ".join(missing)} must be configured '
                'for the cloud_run backend.'
            )

        # Resolve input data URI for the requested dataset.
        if dataset == DatasetType.TEST:
            input_data_uri = getattr(
                self.challenge, 'test_data_gcs_uri', '')
        else:
            input_data_uri = getattr(
                self.challenge, 'validation_data_gcs_uri', '')

        self._check_claim()

        # Resolve code archive bucket and prefix for GCS FUSE.
        archive_uri = self.submission.code_archive_gcs_uri
        archive_path = _gcs_path(archive_uri)
        archive_bucket = archive_path.bucket().name
        archive_key = archive_path.key()

        if not self.submission.started_datetime:
            self._save_submission_field(
                'started_datetime', timezone.now())

        # --- Phase 1: Submission ---
        gcs_mounts = [
            ('/mnt/gcs-archive', archive_bucket, ['ro']),
            ('/mnt/output', bucket, ['rw']),
        ]

        input_env = {}
        if input_data_uri:
            clean_uri = input_data_uri
            if clean_uri.startswith('gs://'):
                clean_uri = clean_uri[5:]
            input_path = _gcs_path(clean_uri)
            input_bucket_name = input_path.bucket().name
            input_key = input_path.key()
            gcs_mounts.append(
                ('/mnt/gcs-input', input_bucket_name, ['ro']))
            input_env['GCS_INPUT_MOUNT'] = (
                f'/mnt/gcs-input/{input_key}')

        predictions_prefix = _gcs_path(
            self._predictions_gcs_prefix).key()
        entrypoint = (
            'set -e; '
            'mkdir -p /workspace /mnt/input /mnt/output-local; '
            'cd /workspace; '
            f"tar xf '/mnt/gcs-archive/{archive_key}' "
            f'2>/dev/null '
            f"|| python -m zipfile -e "
            f"'/mnt/gcs-archive/{archive_key}' .; "
        )
        if input_data_uri:
            entrypoint += (
                'if [ -d "$GCS_INPUT_MOUNT" ]; then '
                '  cp -r "$GCS_INPUT_MOUNT"/. /mnt/input/; '
                'elif tar tf "$GCS_INPUT_MOUNT" '
                '  >/dev/null 2>&1; then '
                '  tar xf "$GCS_INPUT_MOUNT" -C /mnt/input; '
                'else '
                '  python -m zipfile -e '
                '  "$GCS_INPUT_MOUNT" /mnt/input; '
                'fi; '
            )
        entrypoint += (
            f'{self.spec.entrypoint_command}; '
            f"mkdir -p '/mnt/output/{predictions_prefix}'; "
            f'cp -r /mnt/output-local/* '
            f"  '/mnt/output/{predictions_prefix}/'"
        )

        env_vars = {
            'INPUT_DIR': '/mnt/input',
            'OUTPUT_DIR': '/mnt/output-local',
            'SUBMISSION_ID': str(self.submission.pk),
            **input_env,
        }

        vpc_access = None
        if vpc_connector:
            vpc_access = run_v2.VpcAccess(
                connector=vpc_connector,
                egress=run_v2.VpcAccess.VpcEgress.ALL_TRAFFIC,
            )

        # GPU is optional — only requested when the challenge
        # SubmissionSpec has gpu_enabled=True.
        gpu_type = None
        if self.spec.gpu_enabled and self.spec.gpu_type:
            gpu_type = self.spec.gpu_type

        try:
            execution_op = self._create_and_run_job(
                job_name=self.job_name,
                full_job_name=self.full_job_name,
                service_account=submission_sa,
                entrypoint=entrypoint,
                env_vars=env_vars,
                gcs_mounts=gcs_mounts,
                max_runtime_seconds=self.spec.max_runtime_seconds,
                vpc_access=vpc_access,
                gpu_type=gpu_type,
            )
        except Exception as exc:
            message = f'Failed to create submission job: {exc}'
            self._save_run_error(message[:2000], dataset)
            raise RuntimeError(message[:2000])

        self._execution_name = execution_op.metadata.name
        self.submission.cloud_run_job_name = self.job_name
        self.submission.cloud_run_execution_name = (
            self._execution_name)
        self.submission.save(update_fields=[
            'cloud_run_job_name', 'cloud_run_execution_name',
        ])

        try:
            execution_result = execution_op.result(
                timeout=self.spec.max_runtime_seconds + 60)
        except Exception as exc:
            message = f'Submission container failed: {exc}'
            self._save_run_error(message[:2000], dataset)
            raise RuntimeError(message[:2000])

        if execution_result.failed_count > 0:
            message = (
                'Submission container exited with errors '
                f'(failed tasks: {execution_result.failed_count}).'
            )
            self._save_run_error(message, dataset)
            raise RuntimeError(message)

        logger.info(
            'Submission phase complete for %s',
            self.submission.pk,
        )

        # --- Phase 2: Evaluation ---
        self._check_claim()

        eval_uri = self.spec.evaluation_script_gcs_uri
        if not eval_uri:
            raise RuntimeError(
                'No evaluation script configured. Submissions '
                'cannot be scored without a trusted evaluation '
                'script.'
            )

        if dataset == DatasetType.TEST:
            labels_uri = getattr(
                self.challenge, 'test_labels_gcs_uri', '')
        else:
            labels_uri = getattr(
                self.challenge, 'validation_labels_gcs_uri', '')
        if not labels_uri:
            raise RuntimeError(
                f'No {dataset.label.lower()} labels URI '
                f'configured.'
            )

        eval_path = _gcs_path(eval_uri)
        eval_bucket_name = eval_path.bucket().name
        eval_key = eval_path.key()

        clean_labels = labels_uri
        if clean_labels.startswith('gs://'):
            clean_labels = clean_labels[5:]
        labels_path = _gcs_path(clean_labels)
        labels_bucket_name = labels_path.bucket().name
        labels_key = labels_path.key()

        scores_prefix = _gcs_path(
            self._scores_gcs_prefix).key()

        eval_gcs_mounts = [
            ('/mnt/gcs-eval', eval_bucket_name, ['ro']),
            ('/mnt/gcs-labels', labels_bucket_name, ['ro']),
            ('/mnt/gcs-predictions', bucket, ['ro']),
            ('/mnt/output', eval_bucket, ['rw']),
        ]

        eval_entrypoint = (
            'set -e; '
            'mkdir -p /predictions /labels /eval /output-local; '
            f"cp '/mnt/gcs-eval/{eval_key}' /eval/evaluate.py; "
            f"if [ -d '/mnt/gcs-labels/{labels_key}' ]; then "
            f"  cp -r '/mnt/gcs-labels/{labels_key}'/. "
            f'    /labels/; '
            f"elif tar tf '/mnt/gcs-labels/{labels_key}' "
            f'  >/dev/null 2>&1; then '
            f"  tar xf '/mnt/gcs-labels/{labels_key}' "
            f'  -C /labels; '
            f'else '
            f"  python -m zipfile -e "
            f"'/mnt/gcs-labels/{labels_key}' /labels; "
            f"fi; "
            f"cp -r '/mnt/gcs-predictions/{predictions_prefix}'/. "
            f'  /predictions/; '
            'python /eval/evaluate.py '
            '  /predictions /labels /output-local/scores.json; '
            f"mkdir -p '/mnt/output/{scores_prefix}'; "
            f'cp /output-local/scores.json '
            f"  '/mnt/output/{scores_prefix}/scores.json'"
        )

        eval_env = {
            'SUBMISSION_ID': str(self.submission.pk),
        }

        # VPC restriction on the eval phase is intentional
        # defense-in-depth: eval scripts are trusted but do not need
        # internet access, and restricting egress limits the blast
        # radius if an eval script is compromised.
        try:
            eval_op = self._create_and_run_job(
                job_name=self.eval_job_name,
                full_job_name=self.full_eval_job_name,
                service_account=eval_sa,
                entrypoint=eval_entrypoint,
                env_vars=eval_env,
                gcs_mounts=eval_gcs_mounts,
                max_runtime_seconds=120,
                vpc_access=vpc_access,
            )
        except Exception as exc:
            message = f'Failed to create evaluation job: {exc}'
            self._save_run_error(message[:2000], dataset)
            raise RuntimeError(message[:2000])

        try:
            eval_result = eval_op.result(timeout=180)
        except Exception as exc:
            message = f'Evaluation container failed: {exc}'
            self._save_run_error(message[:2000], dataset)
            raise RuntimeError(message[:2000])

        if eval_result.failed_count > 0:
            message = (
                'Evaluation script failed '
                f'(failed tasks: {eval_result.failed_count}).'
            )
            self._save_run_error(message[:2000], dataset)
            raise RuntimeError(message)

        logger.info(
            'Evaluation phase complete for %s',
            self.submission.pk,
        )

    def poll(self, poll_interval=10, max_polls=360):
        """Verify the execution completed successfully.

        run() already waits via the LRO, so this checks the final
        execution state for callers that resume after a crash.
        """
        if not self._execution_name:
            execution_name = (
                self.submission.cloud_run_execution_name)
            if not execution_name:
                return True
            self._execution_name = execution_name

        from google.api_core import exceptions as gapi_exceptions

        try:
            execution = self.executions_client.get_execution(
                name=self._execution_name,
            )
        except gapi_exceptions.NotFound:
            logger.warning(
                'Execution %s not found', self._execution_name)
            return False

        if execution.reconciling:
            return False

        return execution.failed_count == 0

    def extract_scores(self):
        """Read scores.json from the evaluation output in GCS."""
        scores_uri = f'{self._scores_gcs_prefix}/scores.json'
        scores_path = _gcs_path(scores_uri)
        blob = scores_path.bucket().blob(scores_path.key())

        if not blob.exists():
            raise FileNotFoundError(
                f'scores.json not found at {scores_uri}'
            )

        raw = blob.download_as_text()
        scores = json.loads(raw)
        logger.info(
            'Extracted scores for submission %s: %s',
            self.submission.pk, scores,
        )
        return scores

    def cleanup(self):
        """Delete both Cloud Run Jobs after execution."""
        from google.api_core import exceptions as gapi_exceptions

        for name in [self.full_job_name, self.full_eval_job_name]:
            try:
                self.client.delete_job(name=name)
                logger.info('Cleaned up job %s', name)
            except gapi_exceptions.NotFound:
                pass
            except Exception:
                logger.exception(
                    'Failed to cleanup job %s', name)


class LocalContainerOrchestrator:
    """
    Local Docker-based orchestrator for development and testing.

    Replaces Cloud Run with local Docker execution via docker-py,
    allowing the full submission pipeline to run with docker-compose.
    """

    def __init__(self, submission, attempt_id=None):
        self.submission = submission
        self.attempt_id = attempt_id
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
        path = f'{bucket}/challenges/{self.challenge.slug}/output/{self.submission.pk}'
        return f'{path}/attempts/{self.attempt_id}' if self.attempt_id else path

    def _save_submission_field(self, field, value):
        """Do not let an expired test attempt modify the submission."""
        setattr(self.submission, field, value)
        if self.attempt_id:
            updated = type(self.submission).objects.filter(
                pk=self.submission.pk,
                test_scoring_claim_id=self.attempt_id,
                test_scoring_in_progress=True,
            ).update(**{field: value})
            return updated > 0
        else:
            self.submission.save(update_fields=[field])
            return True

    def _check_claim(self):
        if not self.attempt_id:
            return
        still_held = type(self.submission).objects.filter(
            pk=self.submission.pk,
            test_scoring_claim_id=self.attempt_id,
            test_scoring_in_progress=True,
        ).exists()
        if not still_held:
            raise RuntimeError(
                f'Claim {self.attempt_id} expired for '
                f'submission {self.submission.pk}')

    def _save_run_error(self, message, dataset):
        """Keep official test diagnostics out of participant-visible errors."""
        field = ('test_scoring_error_message' if dataset == DatasetType.TEST
                 else 'error_message')
        self._save_submission_field(field, message)

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

    def run(self, dataset=None):
        """Run the submission container locally using Docker."""
        if dataset is None:
            dataset = DatasetType.VAL

        self._check_claim()

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
        # code. Labels stay separate for the evaluator.
        if dataset == DatasetType.TEST:
            input_data_uri = getattr(
                self.challenge, 'test_data_gcs_uri', '')
        else:
            input_data_uri = getattr(
                self.challenge, 'validation_data_gcs_uri', '')
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

        if not self.submission.started_datetime:
            self._save_submission_field('started_datetime', timezone.now())

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
            message = f'Container timed out after {self.spec.max_runtime_seconds}s.'
            self._save_run_error(message, dataset)
            raise RuntimeError(message)

        exit_code = result.get('StatusCode', -1)
        if exit_code != 0:
            logs = self._container.logs(tail=50).decode('utf-8', errors='replace')
            error_msg = f'Container exited with code {exit_code}.\n{logs}'
            self._save_run_error(error_msg[:2000], dataset)
            raise RuntimeError(error_msg[:2000])

        # Participant code controls the output directory. Reject links
        # and special files before the worker copies or uploads anything.
        _check_output_files(output_dir)

        # Run the evaluation script to score predictions against labels
        self._run_evaluation(output_dir, dataset=dataset)

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

    def _run_evaluation(self, output_dir, dataset=None):
        """
        Download the evaluation script and ground-truth labels from GCS,
        then run the evaluator in an isolated container.

        The container is invoked as:
            python /eval/evaluate.py /predictions /labels /output/scores.json

        It must write a JSON dict of {metric_name: value} to the output.

        Selects the dedicated labels URI for the requested dataset.
        """
        if dataset is None:
            dataset = DatasetType.VAL

        eval_uri = self.spec.evaluation_script_gcs_uri
        if not eval_uri:
            raise RuntimeError(
                'No evaluation script configured. Submissions cannot '
                'be scored without a trusted evaluation script.'
            )

        self._check_claim()

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

        # Download ground-truth labels (only the evaluator sees these).
        labels_dir = os.path.join(self._tmpdir, 'labels')
        os.makedirs(labels_dir, exist_ok=True)
        if dataset == DatasetType.TEST:
            labels_uri = getattr(self.challenge, 'test_labels_gcs_uri', '')
        else:
            labels_uri = getattr(
                self.challenge, 'validation_labels_gcs_uri', '')
        if not labels_uri:
            raise RuntimeError(
                f'No {dataset.label.lower()} labels URI configured. '
                'Upload ground-truth labels before scoring submissions.'
            )
        if labels_uri:
            if labels_uri.startswith('gs://'):
                labels_uri = labels_uri[5:]
            _download_gcs_data(_gcs_path(labels_uri), labels_dir)

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


def get_orchestrator(submission, attempt_id=None):
    """Factory function to select the appropriate container orchestrator."""
    backend = getattr(
        settings, 'CHALLENGE_CONTAINER_BACKEND', 'local_docker')
    if backend == 'cloud_run':
        return ContainerOrchestrator(submission, attempt_id=attempt_id)
    return LocalContainerOrchestrator(submission, attempt_id=attempt_id)
