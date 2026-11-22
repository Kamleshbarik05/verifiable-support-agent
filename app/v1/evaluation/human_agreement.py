"""
evaluation/human_agreement.py
Statistical inter-annotator calibration between human ground-truth labels
and the automated LLM-as-a-judge rubric.
Computes Cohen's Kappa (categorical) and Pearson/Spearman correlation (numeric).
"""

from typing import Any, Dict, List
import numpy as np
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import cohen_kappa_score


def compute_cohens_kappa(
    human_labels: List[Any], judge_labels: List[Any]
) -> Dict[str, float]:
    """
    Computes Cohen's Kappa coefficient (inter-rater agreement).
    Interpreted via Landis & Koch (1977):
    - 0.41 - 0.60: Moderate
    - 0.61 - 0.80: Substantial
    - 0.81 - 1.00: Almost Perfect
    """
    kappa = cohen_kappa_score(human_labels, judge_labels)
    observed_agreement = np.mean(
        [h == j for h, j in zip(human_labels, judge_labels)]
    )

    return {
        "cohens_kappa": round(float(kappa), 4),
        "observed_percent_agreement": round(float(observed_agreement * 100), 2),
    }


def compute_numeric_rubric_correlation(
    human_scores: List[float], judge_scores: List[float]
) -> Dict[str, float]:
    """
    Computes Pearson Correlation (r), Spearman Rank Correlation (rho),
    and Mean Absolute Error (MAE) for 1-5 rubric scores.
    """
    h_arr = np.array(human_scores, dtype=float)
    j_arr = np.array(judge_scores, dtype=float)

    # Pearson correlation (linear alignment)
    if len(h_arr) > 1 and np.std(h_arr) > 0 and np.std(j_arr) > 0:
        p_corr, _ = pearsonr(h_arr, j_arr)
        s_corr, _ = spearmanr(h_arr, j_arr)
    else:
        p_corr, s_corr = 1.0, 1.0

    mae = np.mean(np.abs(h_arr - j_arr))

    return {
        "pearson_correlation_r": round(float(p_corr), 4),
        "spearman_rank_rho": round(float(s_corr), 4),
        "mean_absolute_error_mae": round(float(mae), 4),
    }


def evaluate_human_judge_alignment(
    calibration_records: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Runs full statistical agreement calibration across a dataset of paired human-judge records.

    Expected structure of each record:
    {
        "human_escalation": bool,
        "judge_escalation": bool,
        "human_safety_pass": bool,
        "judge_safety_pass": bool,
        "human_groundedness": int (1-5),
        "judge_groundedness": int (1-5),
        "human_actionability": int (1-5),
        "judge_actionability": int (1-5)
    }
    """
    if not calibration_records:
        return {}

    # 1. Categorical Agreement on Escalation (True/False)
    human_esc = [r["human_escalation"] for r in calibration_records]
    judge_esc = [r["judge_escalation"] for r in calibration_records]
    esc_kappa = compute_cohens_kappa(human_esc, judge_esc)

    # 2. Categorical Agreement on Safety Pass (True/False)
    human_safe = [r.get("human_safety_pass", True) for r in calibration_records]
    judge_safe = [r.get("judge_safety_pass", True) for r in calibration_records]
    safe_kappa = compute_cohens_kappa(human_safe, judge_safe)

    # 3. Numeric Rubric Correlations (Groundedness & Actionability)
    human_ground = [r.get("human_groundedness", 4) for r in calibration_records]
    judge_ground = [r.get("judge_groundedness", 4) for r in calibration_records]
    grounding_corr = compute_numeric_rubric_correlation(human_ground, judge_ground)

    human_action = [r.get("human_actionability", 4) for r in calibration_records]
    judge_action = [r.get("judge_actionability", 4) for r in calibration_records]
    action_corr = compute_numeric_rubric_correlation(human_action, judge_action)

    return {
        "sample_size": len(calibration_records),
        "escalation_decision_agreement": esc_kappa,
        "safety_guardrail_agreement": safe_kappa,
        "groundedness_score_correlation": grounding_corr,
        "actionability_score_correlation": action_corr,
    }