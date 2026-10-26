"""
Evaluation script for the ECG Beat Classification challenge.

Compares participant predictions against ground-truth labels and computes
F1 Score, Accuracy, and Sensitivity metrics.

Usage:
    python evaluate.py <predictions_dir> <labels_dir> <scores_output>

Arguments:
    predictions_dir  Directory containing predictions.json from the submission
    labels_dir       Directory containing labels.csv with ground-truth labels
    scores_output    Path where scores.json should be written
"""
import csv
import json
import sys


def load_labels(labels_dir):
    """Load ground-truth labels from labels.csv."""
    import os
    labels_path = os.path.join(labels_dir, 'labels.csv')
    labels = {}
    with open(labels_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            labels[row['beat_id']] = int(row['label'])
    return labels


def load_predictions(predictions_dir):
    """Load predictions from predictions.json."""
    import os
    pred_path = os.path.join(predictions_dir, 'predictions.json')
    with open(pred_path, 'r') as f:
        return json.load(f)


def main():
    if len(sys.argv) != 4:
        print(
            'Usage: python evaluate.py '
            '<predictions_dir> <labels_dir> <scores_output>',
            file=sys.stderr,
        )
        sys.exit(1)

    predictions_dir = sys.argv[1]
    labels_dir = sys.argv[2]
    scores_output = sys.argv[3]

    labels = load_labels(labels_dir)
    predictions = load_predictions(predictions_dir)

    true_labels = []
    pred_labels = []

    for pred in predictions:
        beat_id = pred['beat_id']
        if beat_id in labels:
            true_labels.append(labels[beat_id])
            pred_labels.append(int(pred['classification']))

    if not true_labels:
        scores = {'F1': 0.0, 'Accuracy': 0.0, 'Sensitivity': 0.0}
    else:
        tp = sum(1 for t, p in zip(true_labels, pred_labels) if t == 1 and p == 1)
        fp = sum(1 for t, p in zip(true_labels, pred_labels) if t == 0 and p == 1)
        fn = sum(1 for t, p in zip(true_labels, pred_labels) if t == 1 and p == 0)
        tn = sum(1 for t, p in zip(true_labels, pred_labels) if t == 0 and p == 0)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * sensitivity / (precision + sensitivity)
              if (precision + sensitivity) > 0 else 0.0)
        accuracy = (tp + tn) / len(true_labels) if true_labels else 0.0

        scores = {
            'F1': round(f1, 4),
            'Accuracy': round(accuracy, 4),
            'Sensitivity': round(sensitivity, 4),
        }

    with open(scores_output, 'w') as f:
        json.dump(scores, f, indent=2)

    print(f'Scores: {scores}')


if __name__ == '__main__':
    main()
