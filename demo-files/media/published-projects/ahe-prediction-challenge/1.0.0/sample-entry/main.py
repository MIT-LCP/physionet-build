"""
Sample entry for the Predicting Acute Hypotensive Episodes challenge.

This script demonstrates the expected interface for a challenge submission.
It reads patient records from the test data directory, generates predictions,
and writes a scores.json file to the output directory.

Environment variables (set automatically by the evaluation environment):
    INPUT_DIR  - directory containing test CSV files
    OUTPUT_DIR - directory where scores.json should be written

Usage:
    python main.py
"""
import csv
import json
import os
import statistics


def load_record(filepath):
    """Load a patient record CSV and return a list of row dicts."""
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        return list(reader)


def predict(record):
    """
    Generate a prediction for a single patient record.

    This baseline computes the mean MAP (Mean Arterial Pressure) across
    all timestamps and predicts an AHE if the mean MAP falls below 65 mmHg.

    Returns:
        prediction (int): 1 if AHE predicted, 0 otherwise
        risk_score (float): continuous risk score between 0 and 1
    """
    map_values = []
    for row in record:
        try:
            val = float(row['MAP'])
            map_values.append(val)
        except (ValueError, KeyError):
            continue

    if not map_values:
        return 0, 0.5

    mean_map = statistics.mean(map_values)

    # Simple threshold-based risk score: lower MAP = higher risk.
    # MAP typically ranges from ~40 to ~120.
    risk_score = max(0.0, min(1.0, (80.0 - mean_map) / 40.0))

    prediction = 1 if mean_map < 65.0 else 0
    return prediction, round(risk_score, 4)


def main():
    input_dir = os.environ.get('INPUT_DIR', '/data/test')
    output_dir = os.environ.get('OUTPUT_DIR', '/output')

    os.makedirs(output_dir, exist_ok=True)

    results = []
    for filename in sorted(os.listdir(input_dir)):
        if not filename.endswith('.csv'):
            continue

        record_id = os.path.splitext(filename)[0]
        filepath = os.path.join(input_dir, filename)
        record = load_record(filepath)
        prediction, risk_score = predict(record)

        results.append({
            'record_id': record_id,
            'prediction': prediction,
            'risk_score': risk_score,
        })

    # Write results as scores.json
    output_path = os.path.join(output_dir, 'scores.json')
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'Wrote {len(results)} predictions to {output_path}')


if __name__ == '__main__':
    main()
