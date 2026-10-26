"""
Demo submission: reads ECG beats and writes random classifications.

This is a minimal example used for local development and testing.
"""
import csv
import json
import os
import random

random.seed(42)

input_dir = os.environ.get('INPUT_DIR', '/mnt/input')
output_dir = os.environ.get('OUTPUT_DIR', '/mnt/output')

predictions = []

for patient_id in sorted(os.listdir(input_dir)):
    patient_dir = os.path.join(input_dir, patient_id)
    if not os.path.isdir(patient_dir):
        continue
    record_path = os.path.join(patient_dir, 'record.csv')
    if not os.path.exists(record_path):
        continue
    with open(record_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            predictions.append({
                'beat_id': row['beat_id'],
                'classification': random.randint(0, 1),
            })

if not predictions:
    predictions.append({
        'beat_id': 'beat_001',
        'classification': 0,
    })

os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, 'predictions.json')
with open(output_path, 'w') as f:
    json.dump(predictions, f, indent=2)

print(f'Wrote {len(predictions)} prediction(s) to {output_path}')
