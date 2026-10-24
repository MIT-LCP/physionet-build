"""
Sample entry for the ECG Beat Classification challenge.

This script demonstrates the expected interface for a challenge submission.
It reads ECG beat segments from per-patient record files, classifies each
beat as Normal (0) or Abnormal (1), and writes a predictions.json file to
the output directory.

The predictions.json file must be a list of objects, each with:
    - beat_id: identifier matching the beat_id column in the input CSV
    - classification: binary classification (0 = Normal, 1 = Abnormal)

The evaluation pipeline will then compare these classifications against
ground-truth labels to compute the final scores.

Environment variables (set automatically by the evaluation environment):
    INPUT_DIR  - directory containing patient subdirectories
    OUTPUT_DIR - directory where predictions.json should be written

Usage:
    python main.py
"""
import csv
import json
import os
import statistics


def load_beats(filepath):
    """Load ECG beat segments from a CSV file."""
    beats = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            beats.append(row)
    return beats


def classify_beat(row):
    """
    Classify a single ECG beat segment.

    This baseline uses a simple amplitude-range heuristic: normal sinus
    beats typically have one dominant R-peak, producing a large max-to-min
    range, while many abnormal beats (e.g. premature ventricular
    contractions) show a wider, lower-amplitude morphology.

    Returns:
        classification (int): 1 if abnormal, 0 if normal
    """
    samples = []
    for key, value in row.items():
        if key.startswith('sample_'):
            try:
                samples.append(float(value))
            except ValueError:
                continue

    if not samples:
        return 0

    peak = max(samples)
    trough = min(samples)
    amplitude_range = peak - trough

    mean_val = statistics.mean(samples)
    above_mean = sum(1 for s in samples if s > mean_val)
    peak_ratio = above_mean / len(samples)

    if amplitude_range < 0.7 and peak_ratio > 0.35:
        return 1
    return 0


def main():
    input_dir = os.environ.get('INPUT_DIR', '/data/test')
    output_dir = os.environ.get('OUTPUT_DIR', '/output')

    os.makedirs(output_dir, exist_ok=True)

    results = []
    for patient_id in sorted(os.listdir(input_dir)):
        patient_dir = os.path.join(input_dir, patient_id)
        if not os.path.isdir(patient_dir):
            continue

        record_path = os.path.join(patient_dir, 'record.csv')
        if not os.path.exists(record_path):
            continue

        beats = load_beats(record_path)
        for row in beats:
            beat_id = row['beat_id']
            classification = classify_beat(row)
            results.append({
                'beat_id': beat_id,
                'classification': classification,
            })

    output_path = os.path.join(output_dir, 'predictions.json')
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'Wrote {len(results)} predictions to {output_path}')


if __name__ == '__main__':
    main()
