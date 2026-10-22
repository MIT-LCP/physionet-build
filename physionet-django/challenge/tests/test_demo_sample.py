"""Check that the downloadable demo entry matches the scoring fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from unittest import mock

from django.test import SimpleTestCase, override_settings

from challenge.management.commands.seed_challenge_data import Command


REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_FILES = (
    REPO_ROOT / 'demo-files/media/published-projects'
    / 'demo-ecg-challenge/1.0.0'
)
SAMPLE_SOURCE = REPO_ROOT / 'physionet-django/challenge/fixtures/demo-sample-entry'
PRIVATE_FILES = (
    REPO_ROOT / 'physionet-django/challenge/fixtures/demo-submission-files'
)


class DemoSampleTests(SimpleTestCase):
    @override_settings(
        CHALLENGE_STORAGE_EMULATOR_HOST='http://fake-gcs',
        CHALLENGE_STAGING_BUCKET='challenge-staging',
    )
    @mock.patch('challenge.models.Submission.objects.filter')
    @mock.patch('challenge.models.Challenge.objects.get')
    @mock.patch('challenge.management.commands.seed_challenge_data.storage.Client')
    def test_reseeding_removes_old_validation_labels(
            self, storage_client, get_challenge, submissions):
        challenge = mock.MagicMock()
        challenge.validation_data_gcs_uri = 'challenge-staging/demo/validation/'
        challenge.validation_labels_gcs_uri = (
            'challenge-staging/demo/validation_labels/')
        challenge.test_data_gcs_uri = 'challenge-staging/demo/test/'
        challenge.test_labels_gcs_uri = 'challenge-staging/demo/test_labels/'
        challenge.submission_spec.evaluation_script_gcs_uri = (
            'challenge-staging/demo/evaluation/evaluate.py')
        get_challenge.return_value = challenge
        submissions.return_value = []

        bucket = storage_client.return_value.get_bucket.return_value
        storage_client.return_value.bucket.return_value = bucket
        blobs = {}
        bucket.blob.side_effect = lambda key: blobs.setdefault(
            key, mock.MagicMock())

        with mock.patch.dict(os.environ):
            Command().handle()

        old_labels = blobs['demo/validation/labels.csv']
        old_labels.delete.assert_called_once_with()
        old_labels.upload_from_filename.assert_not_called()
        blobs['demo/validation/records.csv'].upload_from_filename.assert_called_once()
        blobs['demo/validation_labels/labels.csv'].upload_from_filename.assert_called_once()

    def test_seeded_validation_input_contains_only_records(self):
        bucket = mock.MagicMock()
        validation_dir = PRIVATE_FILES / 'validation'

        self.assertEqual(
            Command()._upload_dir(bucket, validation_dir, 'validation/'), 1)
        bucket.blob.assert_called_once_with('validation/records.csv')
        self.assertEqual(
            sorted(path.name for path in validation_dir.iterdir()),
            ['records.csv'],
        )

    def test_downloadable_archive_contains_current_main_at_root(self):
        with tarfile.open(PUBLIC_FILES / 'sample-entry.tar.gz', 'r:gz') as archive:
            self.assertEqual(archive.getnames(), ['README.txt', 'main.py'])
            archived_main = archive.extractfile('main.py').read()
        self.assertEqual(
            archived_main, (SAMPLE_SOURCE / 'main.py').read_bytes())

    def run_entry(self, input_dir, output_dir):
        env = os.environ.copy()
        env['INPUT_DIR'] = str(input_dir)
        env['OUTPUT_DIR'] = str(output_dir)
        subprocess.run(
            [sys.executable, str(SAMPLE_SOURCE / 'main.py')],
            env=env, check=True, capture_output=True,
        )
        return json.loads((output_dir / 'predictions.json').read_text())

    def test_public_example_excludes_training_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            predictions = self.run_entry(
                PUBLIC_FILES / 'training-data', Path(temp_dir))
        self.assertEqual(
            [item['record_id'] for item in predictions],
            ['patient_001', 'patient_002'],
        )

    def test_entry_can_score_private_validation_example(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            predictions = self.run_entry(
                PRIVATE_FILES / 'validation', output_dir)
            self.assertEqual(
                [item['record_id'] for item in predictions], ['records'])

            scores_path = output_dir / 'scores.json'
            subprocess.run([
                sys.executable,
                str(PRIVATE_FILES / 'evaluation/evaluate.py'),
                str(output_dir),
                str(PRIVATE_FILES / 'validation_labels'),
                str(scores_path),
            ], check=True, capture_output=True)
            scores = json.loads(scores_path.read_text())

        self.assertEqual(set(scores), {'AUROC', 'Sensitivity', 'PPV'})
