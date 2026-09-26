"""
Upload demo test data to fake GCS when STORAGE_EMULATOR_HOST is set.

Usage: python manage.py seed_challenge_data

1. Creates the staging bucket if it doesn't exist
2. Uploads files from fixtures/demo-submission-files/test_data/ to the
   challenge's test_data_gcs_uri path
"""
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from google.cloud import storage


class Command(BaseCommand):
    help = 'Upload demo challenge test data to the fake GCS staging bucket.'

    def handle(self, *args, **options):
        emulator_host = os.environ.get('STORAGE_EMULATOR_HOST', '')
        if not emulator_host:
            raise CommandError(
                'STORAGE_EMULATOR_HOST is not set. This command is only '
                'intended for local development with the fake GCS server.'
            )

        bucket_name = getattr(settings, 'CHALLENGE_STAGING_BUCKET', 'challenge-staging')

        client = storage.Client(
            project='test',
            credentials=None,
        )

        # Create the staging bucket if it doesn't exist.
        try:
            client.get_bucket(bucket_name)
            self.stdout.write(f'Bucket "{bucket_name}" already exists.')
        except Exception:
            client.create_bucket(bucket_name)
            self.stdout.write(self.style.SUCCESS(
                f'Created bucket "{bucket_name}".'
            ))

        bucket = client.bucket(bucket_name)

        # Upload test data files.
        fixtures_dir = Path(__file__).resolve().parent.parent.parent / 'fixtures'
        test_data_dir = fixtures_dir / 'demo-submission-files' / 'test_data'

        if not test_data_dir.exists():
            raise CommandError(f'Test data directory not found: {test_data_dir}')

        from challenge.models import Challenge
        try:
            challenge = Challenge.objects.get(slug='ahe-prediction-challenge')
        except Challenge.DoesNotExist:
            raise CommandError(
                'Demo challenge not found. Run "python manage.py loaddemo" first.'
            )

        # Upload to the test_data_gcs_uri path.
        test_prefix = challenge.test_data_gcs_uri
        # Strip the bucket name prefix if present.
        if test_prefix.startswith(f'{bucket_name}/'):
            test_prefix = test_prefix[len(f'{bucket_name}/'):]

        uploaded = 0
        for filepath in test_data_dir.rglob('*'):
            if filepath.is_file():
                relative = filepath.relative_to(test_data_dir)
                blob_name = f'{test_prefix}{relative}'
                blob = bucket.blob(blob_name)
                blob.upload_from_filename(str(filepath))
                self.stdout.write(f'  Uploaded {relative} -> {blob_name}')
                uploaded += 1

        self.stdout.write(self.style.SUCCESS(
            f'Uploaded {uploaded} file(s) to "{bucket_name}".'
        ))
