"""
Upload demo challenge data to fake GCS when STORAGE_EMULATOR_HOST is set.

Usage: python manage.py seed_challenge_data

For each demo challenge found in the database:
1. Creates the staging bucket if it doesn't exist
2. Uploads test data and validation data (input records only)
3. Uploads separate validation and test ground-truth labels
4. Uploads the evaluation script
5. Uploads a code archive for each demo submission
"""
import io
import os
import tarfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from google.cloud import storage

CHALLENGE_FIXTURES = {
    'demo-ecg-challenge': 'demo-submission-files',
    'demo-waveform-challenge': 'waveform-submission-files',
}


class Command(BaseCommand):
    help = 'Upload demo challenge data to the fake GCS staging bucket.'

    def handle(self, *args, **options):
        emulator_host = getattr(
            settings, 'CHALLENGE_STORAGE_EMULATOR_HOST', '')
        if not emulator_host:
            raise CommandError(
                'CHALLENGE_STORAGE_EMULATOR_HOST is not set. This command '
                'is only for local development with the fake GCS server.'
            )

        # Ensure the env var is set for the google-cloud-storage SDK.
        os.environ['STORAGE_EMULATOR_HOST'] = emulator_host

        staging_bucket_name = getattr(
            settings, 'CHALLENGE_STAGING_BUCKET', 'challenge-staging')
        eval_bucket_name = getattr(
            settings, 'CHALLENGE_EVAL_BUCKET', 'challenge-evaluation')

        client = storage.Client(
            project='test',
            credentials=None,
        )

        for name in [staging_bucket_name, eval_bucket_name]:
            try:
                client.get_bucket(name)
                self.stdout.write(f'Bucket "{name}" already exists.')
            except Exception:
                client.create_bucket(name)
                self.stdout.write(self.style.SUCCESS(
                    f'Created bucket "{name}".'
                ))

        staging_bucket = client.bucket(staging_bucket_name)
        eval_bucket = client.bucket(eval_bucket_name)
        fixtures_dir = Path(__file__).resolve().parent.parent.parent / 'fixtures'

        from challenge.models import Challenge, Submission

        total_uploaded = 0
        for slug, files_dir_name in CHALLENGE_FIXTURES.items():
            try:
                challenge = Challenge.objects.get(slug=slug)
            except Challenge.DoesNotExist:
                continue

            demo_dir = fixtures_dir / files_dir_name
            if not demo_dir.exists():
                continue

            spec = challenge.submission_spec
            uploaded = 0

            staging_prefix = f'{staging_bucket_name}/'
            eval_prefix_str = f'{eval_bucket_name}/'

            def strip_bucket(uri):
                for prefix in [staging_prefix, eval_prefix_str]:
                    if uri.startswith(prefix):
                        return uri[len(prefix):]
                return uri

            # Upload test data (input records only) → staging
            test_data_dir = demo_dir / 'test_data'
            if test_data_dir.exists():
                prefix = strip_bucket(challenge.test_data_gcs_uri)
                uploaded += self._upload_dir(
                    staging_bucket, test_data_dir, prefix)

            # Upload validation data (input records only) → staging
            validation_dir = demo_dir / 'validation'
            if validation_dir.exists():
                prefix = strip_bucket(
                    challenge.validation_data_gcs_uri)
                old_labels = staging_bucket.blob(
                    f'{prefix}labels.csv')
                if old_labels.exists():
                    old_labels.delete()
                uploaded += self._upload_dir(
                    staging_bucket, validation_dir, prefix)

            # Upload validation labels → eval bucket
            validation_labels_dir = demo_dir / 'validation_labels'
            if (validation_labels_dir.exists()
                    and challenge.validation_labels_gcs_uri):
                prefix = strip_bucket(
                    challenge.validation_labels_gcs_uri)
                uploaded += self._upload_dir(
                    eval_bucket, validation_labels_dir, prefix)

            # Upload test labels → eval bucket
            test_labels_dir = demo_dir / 'test_labels'
            if (test_labels_dir.exists()
                    and challenge.test_labels_gcs_uri):
                prefix = strip_bucket(
                    challenge.test_labels_gcs_uri)
                uploaded += self._upload_dir(
                    eval_bucket, test_labels_dir, prefix)

            # Upload evaluation script → eval bucket
            eval_dir = demo_dir / 'evaluation'
            if eval_dir.exists() and spec.evaluation_script_gcs_uri:
                eval_uri = strip_bucket(
                    spec.evaluation_script_gcs_uri)
                eval_prefix = eval_uri.rsplit('/', 1)[0] + '/'
                uploaded += self._upload_dir(
                    eval_bucket, eval_dir, eval_prefix)

            # Upload code archive for each demo submission → staging
            code_archive_dir = demo_dir / 'code_archive'
            if code_archive_dir.exists():
                archive_data = self._create_tar_gz(code_archive_dir)
                submissions = Submission.objects.filter(
                    challenge=challenge)
                for submission in submissions:
                    if not submission.code_archive_gcs_uri:
                        continue
                    gcs_key = strip_bucket(
                        submission.code_archive_gcs_uri)
                    blob = staging_bucket.blob(gcs_key)
                    blob.upload_from_file(
                        io.BytesIO(archive_data), rewind=True)
                    self.stdout.write(
                        f'  Uploaded code archive -> {gcs_key}')
                    uploaded += 1

            self.stdout.write(self.style.SUCCESS(
                f'Uploaded {uploaded} file(s) for {slug}.'
            ))
            total_uploaded += uploaded

        if not total_uploaded:
            self.stdout.write(self.style.WARNING(
                'No demo challenges found. Run "python manage.py loaddemo" first.'
            ))

    def _create_tar_gz(self, source_dir):
        """Create a tar.gz archive from a directory and return bytes."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            for filepath in source_dir.rglob('*'):
                if filepath.is_file():
                    arcname = filepath.relative_to(source_dir)
                    tar.add(str(filepath), arcname=str(arcname))
        return buf.getvalue()

    def _upload_dir(self, bucket, local_dir, gcs_prefix):
        """Upload all files in local_dir to bucket under gcs_prefix."""
        count = 0
        for filepath in local_dir.rglob('*'):
            if filepath.is_file():
                relative = filepath.relative_to(local_dir)
                blob_name = f'{gcs_prefix}{relative}'
                blob = bucket.blob(blob_name)
                blob.upload_from_filename(str(filepath))
                self.stdout.write(f'  Uploaded {relative} -> {blob_name}')
                count += 1
        return count
