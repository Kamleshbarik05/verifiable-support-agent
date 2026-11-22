"""
evaluation/metrics.py
Statistical evaluation metrics for intent classification, escalation triage,
and response grounding.
"""

from typing import Any, Dict, List
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score


def compute_intent_metrics(
    y_true: List[str], y_pred: List[str]
) -> Dict[str, float]:
    """
    Computes Accuracy, Macro-Precision, Macro-Recall, and Macro-F1 for Intent Classification.
    Macro-F1 is preferred over micro-accuracy due to intent class imbalance.
    """
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_precision": round(
            float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 4
        ),
        "macro_recall": round(
            float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 4
        ),
        "macro_f1": round(
            float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4
        ),
    }


def compute_escalation_metrics(
    y_true: List[bool], y_pred: List[bool]
) -> Dict[str, float]:
    """
    Computes Precision, Recall, F1, and critical False Negative Rate (FNR) for Escalation.

    In Customer Support:
    - False Positive (FP): Auto-handleable query escalated to human (costs human agent time).
    - False Negative (FN): Safety/legal risk auto-handled by bot (catastrophic failure).
    - FNR = FN / (FN + TP) -> Must be as close to 0.0 as possible!
    """
    y_true_arr = np.array(y_true, dtype=bool)
    y_pred_arr = np.array(y_pred, dtype=bool)

    tp = np.sum((y_true_arr == True) & (y_pred_arr == True))
    fp = np.sum((y_true_arr == False) & (y_pred_arr == True))
    fn = np.sum((y_true_arr == True) & (y_pred_arr == False))
    tn = np.sum((y_true_arr == False) & (y_pred_arr == False))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    return {
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "false_negative_rate": round(float(fnr), 4),
        "total_escalations_flagged": int(tp + fp),
        "true_positives": int(tp),
        "false_negatives": int(fn),
    }


def compute_grounding_lexical_overlap(
    drafted_replies: List[str], reference_resolutions: List[str]
) -> Dict[str, float]:
    """
    Measures token-level Jaccard word overlap between drafted replies
    and the gold reference resolutions.
    """
    scores = []
    for drafted, gold in zip(drafted_replies, reference_resolutions):
        draft_tokens = set(drafted.lower().split())
        gold_tokens = set(gold.lower().split())
        if not draft_tokens or not gold_tokens:
            scores.append(0.0)
            continue
        intersection = len(draft_tokens & gold_tokens)
        union = len(draft_tokens | gold_tokens)
        scores.append(intersection / union if union > 0 else 0.0)

    return {
        "mean_jaccard_overlap": round(float(np.mean(scores)), 4),
        "median_jaccard_overlap": round(float(np.median(scores)), 4),
    }
