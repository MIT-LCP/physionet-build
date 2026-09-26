"""
Evaluation script for the Predicting Acute Hypotensive Episodes challenge.

Compares participant predictions against ground-truth labels and computes
AUROC, Sensitivity, and PPV metrics.

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
            labels[row['record_id']] = int(row['label'])
    return labels


def load_predictions(predictions_dir):
    """Load predictions from predictions.json."""
    import os
    pred_path = os.path.join(predictions_dir, 'predictions.json')
    with open(pred_path, 'r') as f:
        return json.load(f)


def compute_auroc(labels, risk_scores):
    """
    Compute AUROC using the trapezoidal rule.

    For a single-sample case or when all labels are the same class,
    returns the mean risk score as a fallback.
    """
    if not labels or len(set(labels)) < 2:
        # Cannot compute a meaningful AUROC with only one class.
        # Return mean risk score as a proxy.
        return sum(risk_scores) / len(risk_scores) if risk_scores else 0.0

    # Sort by risk score descending
    paired = sorted(zip(risk_scores, labels), key=lambda x: -x[0])
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos

    tp = 0
    fp = 0
    auc = 0.0
    prev_fpr = 0.0

    for score, label in paired:
        if label == 1:
            tp += 1
        else:
            fp += 1
            tpr = tp / n_pos
            fpr = fp / n_neg
            auc += (fpr - prev_fpr) * tpr
            prev_fpr = fpr

    return round(auc, 4)


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

    # Match predictions to labels
    true_labels = []
    pred_labels = []
    risk_scores = []

    for pred in predictions:
        record_id = pred['record_id']
        if record_id in labels:
            true_labels.append(labels[record_id])
            pred_labels.append(int(pred['prediction']))
            risk_scores.append(float(pred['risk_score']))

    if not true_labels:
        scores = {'AUROC': 0.0, 'Sensitivity': 0.0, 'PPV': 0.0}
    else:
        # AUROC
        auroc = compute_auroc(true_labels, risk_scores)

        # Sensitivity = TP / (TP + FN)
        tp = sum(1 for t, p in zip(true_labels, pred_labels) if t == 1 and p == 1)
        fn = sum(1 for t, p in zip(true_labels, pred_labels) if t == 1 and p == 0)
        sensitivity = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0

        # PPV = TP / (TP + FP)
        fp = sum(1 for t, p in zip(true_labels, pred_labels) if t == 0 and p == 1)
        ppv = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0

        scores = {
            'AUROC': auroc,
            'Sensitivity': sensitivity,
            'PPV': ppv,
        }

    with open(scores_output, 'w') as f:
        json.dump(scores, f, indent=2)

    print(f'Scores: {scores}')


if __name__ == '__main__':
    main()
