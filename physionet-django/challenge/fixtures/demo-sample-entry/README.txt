Sample Entry: Predicting Acute Hypotensive Episodes
====================================================

This directory contains a sample submission that can be used as a
starting point for the challenge.
The training-data/ directory in the project files contains two synthetic
records and labels for trying it locally.

Files
-----
- main.py : The entry point script that reads test data and writes
             predictions to predictions.json.

How it works
------------
The sample entry uses a simple threshold-based approach:

1. For each patient record, it computes the mean MAP (Mean Arterial
   Pressure) across all available timestamps.
2. If the mean MAP is below 65 mmHg, it predicts an acute hypotensive
   episode (AHE).
3. A continuous risk score is derived by linearly mapping MAP values
   into the [0, 1] range.

The evaluation pipeline then compares these predictions against the
ground-truth labels to compute AUROC, Sensitivity, and PPV.

How to submit
-------------
Upload the downloaded sample-entry.tar.gz archive unchanged through the
challenge submission page.

If you modify the source, package it into a .tar.gz or .zip archive with
main.py at the top level and keep that filename unchanged:

       tar czf submission.tar.gz main.py

Upload the resulting archive through the challenge submission page.

To try the sample locally after extracting the archive, set INPUT_DIR to the
training-data/ directory downloaded from the project Files section:

       INPUT_DIR=/path/to/training-data OUTPUT_DIR=/tmp/ahe-demo-output python main.py

The script writes predictions.json to OUTPUT_DIR. The labels.csv file in
training-data/ is for local inspection and is not an input to the submission.

Your container will have the following environment variables set:
- INPUT_DIR  : path to the directory containing test CSV files
- OUTPUT_DIR : path where your code should write predictions.json

Output format
-------------
Your code must write a predictions.json file containing a list of
objects, each with:

    [
      {"record_id": "patient_001", "prediction": 0, "risk_score": 0.12},
      {"record_id": "patient_002", "prediction": 1, "risk_score": 0.87}
    ]

- record_id  : matches the input CSV filename (without .csv extension)
- prediction : binary prediction (0 or 1)
- risk_score : continuous value between 0 and 1

Requirements
------------
The sample entry uses only the Python standard library (csv, json,
os, statistics).
