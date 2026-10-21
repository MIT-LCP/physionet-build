"""
Demo submission: reads input records and writes random predictions.

This is a minimal example used for local development and testing.
"""
import csv
import json
import os
import random

random.seed(42)

input_dir = os.environ.get('INPUT_DIR', '/mnt/input')
output_dir = os.environ.get('OUTPUT_DIR', '/mnt/output')

# Read input records
records_path = os.path.join(input_dir, 'records.csv')
predictions = []

if os.path.exists(records_path):
    with open(records_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            record_id = row.get('record_id', row.get('timestamp', 'unknown'))
            risk_score = round(random.random(), 4)
            predictions.append({
                'record_id': record_id,
                'prediction': 1 if risk_score > 0.5 else 0,
                'risk_score': risk_score,
            })
else:
    # Fallback: generate a single dummy prediction
    predictions.append({
        'record_id': 'records',
        'prediction': 1,
        'risk_score': 0.75,
    })

# Write predictions
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, 'predictions.json')
with open(output_path, 'w') as f:
    json.dump(predictions, f, indent=2)

print(f'Wrote {len(predictions)} prediction(s) to {output_path}')
