Sample Entry: Predicting Acute Hypotensive Episodes
====================================================

This directory contains a sample submission that can be used as a
starting point for the challenge.

Files
-----
- main.py : The entry point script that reads test data and writes
             predictions to scores.json.

How it works
------------
The sample entry uses a simple threshold-based approach:

1. For each patient record, it computes the mean MAP (Mean Arterial
   Pressure) across all available timestamps.
2. If the mean MAP is below 65 mmHg, it predicts an acute hypotensive
   episode (AHE).
3. A continuous risk score is derived by linearly mapping MAP values
   into the [0, 1] range.

How to submit
-------------
1. Package your code into a .tar.gz archive:

       tar czf submission.tar.gz main.py

2. Upload the archive through the challenge submission page.

Your container will have the following environment variables set:
- INPUT_DIR  : path to the directory containing test CSV files
- OUTPUT_DIR : path where your code should write scores.json

Requirements
------------
The sample entry uses only the Python standard library (csv, json,
os, statistics). If your submission needs additional packages, include
a requirements.txt and install them in your entrypoint script.
