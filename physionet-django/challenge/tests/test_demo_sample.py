"""Check that the downloadable demo entry matches the scoring fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from django.test import SimpleTestCase


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
