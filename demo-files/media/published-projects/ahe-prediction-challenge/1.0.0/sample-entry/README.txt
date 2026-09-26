Sample Entry: Predicting Acute Hypotensive Episodes
====================================================

This directory contains a sample submission that can be used as a
starting point for the challenge.

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
1. Package your code into a .tar.gz or .zip archive:

       tar czf submission.tar.gz main.py

2. Upload the archive through the challenge submission page.

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
os, statistics). If your submission needs additional packages, include
a requirements.txt and install them in your entrypoint script.
