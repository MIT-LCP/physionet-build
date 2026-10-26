Sample Entry: ECG Beat Classification
======================================

This directory contains a sample submission that can be used as a
starting point for the challenge.
The training-data/ directory in the project files contains sample beat
segments and labels for trying it locally.

Files
-----
- main.py : The entry point script that reads beat data and writes
             classifications to predictions.json.

How it works
------------
The sample entry uses a simple amplitude-range heuristic:

1. For each patient's record, it reads the beat segments and extracts
   the 20 amplitude samples per beat.
2. It computes the peak-to-trough amplitude range and the fraction of
   samples above the mean.
3. Normal sinus beats typically have one dominant R-peak with a large
   amplitude range; abnormal beats (e.g. PVCs) tend to show a wider,
   lower-amplitude morphology.

The evaluation pipeline then compares these classifications against the
ground-truth labels to compute F1, Accuracy, and Sensitivity.

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

       INPUT_DIR=/path/to/training-data OUTPUT_DIR=/tmp/ecg-demo-output python main.py

The script writes predictions.json to OUTPUT_DIR. The labels.csv file in
training-data/ is for local inspection and is not an input to the submission.

Your container will have the following environment variables set:
- INPUT_DIR  : path to the directory containing patient subdirectories
- OUTPUT_DIR : path where your code should write predictions.json

Output format
-------------
Your code must write a predictions.json file containing a list of
objects, each with:

    [
      {"beat_id": "beat_001", "classification": 0},
      {"beat_id": "beat_002", "classification": 1}
    ]

- beat_id         : matches the beat_id column in the input CSV
- classification  : 0 for Normal, 1 for Abnormal

Requirements
------------
The sample entry uses only the Python standard library (csv, json,
os, statistics).
