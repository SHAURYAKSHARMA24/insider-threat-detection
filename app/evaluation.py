"""Labelled scenario evaluation for the detector (Phase 9, Objective 4).

This module compares detector predictions with ground-truth labels row by row.
It deliberately performs no ingestion and no anomaly storage: scenario CSV rows
are scored in memory against the existing persisted per-user baselines.
"""
from pathlib import Path

from app.anomalies import classify_severity
from app.config import Config
from app.db import connect
from app.ingest import load_csv, validate_rows
from app.scoring import score_record

LABEL_ANOMALOUS = "anomalous"
DEFAULT_THRESHOLDS = (2.0, 2.5, 3.0, 3.5, 4.0)


def _latest_baselines(db_path):
    """Load the newest baseline row for every user from ``db_path``."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT b.* FROM Baselines b "
            "JOIN (SELECT user_id, MAX(baseline_id) AS latest "
            "      FROM Baselines GROUP BY user_id) m "
            "ON b.baseline_id = m.latest "
            "ORDER BY b.user_id"
        ).fetchall()
        return {row["user_id"]: dict(row) for row in rows}
    finally:
        conn.close()


def _is_actual_anomaly(label):
    """Return True when a scenario label denotes ground-truth anomaly."""
    return str(label).strip().lower() == LABEL_ANOMALOUS


def _severity_for_prediction(score, threshold):
    """Return a severity string for a predicted anomaly, preserving existing bands."""
    if score is None or score < threshold:
        return None
    severity = classify_severity(score)
    if severity is not None:
        return severity
    # Threshold sensitivity can evaluate below Config.Z_LOW. In that case the
    # record is a predicted anomaly for evaluation, but would not be stored by
    # the configured detector. Keep the label conservative and explicit.
    return "Low"


def run_scenario(scenario_csv, db_path=None, threshold=None, scenario_name=None):
    """Score a labelled scenario CSV against existing baselines.

    Args:
        scenario_csv: path to a CSV containing the normal activity columns plus
            ``label`` with values ``normal`` or ``anomalous``.
        db_path: SQLite database containing the ``Baselines`` table. Defaults
            to :attr:`app.config.Config.DB_PATH`.
        threshold: prediction threshold. Defaults to ``Config.Z_LOW``.
        scenario_name: optional name copied into every result row.

    Returns:
        A list of row-level prediction dictionaries. Rows with no matching
        baseline are retained with ``predicted_anomaly=False`` and
        ``skip_reason='no_baseline'`` so metrics remain row aligned.
    """
    if db_path is None:
        db_path = Config.DB_PATH
    if threshold is None:
        threshold = Config.Z_LOW

    path = Path(scenario_csv)
    df = load_csv(path)
    if "label" not in df.columns:
        raise ValueError("Scenario CSV must include a label column")
    clean, rejected = validate_rows(df)
    if not rejected.empty:
        reasons = rejected["rejection_reason"].value_counts().to_dict()
        raise ValueError(f"Scenario CSV contains invalid rows: {reasons}")

    baselines = _latest_baselines(db_path)
    results = []
    name = scenario_name or path.stem

    for row_number, row in enumerate(clean.to_dict(orient="records"), start=1):
        record = {
            "user_id": row["user_id"],
            "login_time": row["login_time"],
            "access_count": int(row["access_count"]),
            "resource_type": row["resource_type"],
        }
        baseline = baselines.get(record["user_id"])
        actual_anomaly = _is_actual_anomaly(row["label"])

        result = {
            "scenario": name,
            "row_number": row_number,
            "user_id": row["user_id"],
            "user_name": row["user_name"],
            "user_role": row["user_role"],
            "activity_date": row["activity_date"],
            "login_time": row["login_time"],
            "access_count": int(row["access_count"]),
            "resource_type": row["resource_type"],
            "actual_label": row["label"],
            "actual_anomaly": actual_anomaly,
            "predicted_anomaly": False,
            "responsible_feature": None,
            "score": None,
            "severity": None,
            "reason": None,
            "skip_reason": None,
        }

        if baseline is None:
            result["skip_reason"] = "no_baseline"
            results.append(result)
            continue

        scored = score_record(record, baseline)
        score = scored["deviation_score"]
        predicted = score >= threshold

        result.update(
            {
                "predicted_anomaly": predicted,
                "responsible_feature": scored["responsible_feature"],
                "score": score,
                "severity": _severity_for_prediction(score, threshold) if predicted else None,
                "reason": scored["reason"],
            }
        )
        results.append(result)

    return results


def confusion_matrix(rows):
    """Compute TP/FP/TN/FN counts from row-level evaluation output."""
    matrix = {"true_positives": 0, "false_positives": 0, "true_negatives": 0, "false_negatives": 0}
    for row in rows:
        actual = bool(row["actual_anomaly"])
        predicted = bool(row["predicted_anomaly"])
        if actual and predicted:
            matrix["true_positives"] += 1
        elif not actual and predicted:
            matrix["false_positives"] += 1
        elif not actual and not predicted:
            matrix["true_negatives"] += 1
        else:
            matrix["false_negatives"] += 1
    return matrix


def metrics(rows_or_matrix):
    """Compute evaluation metrics with clean zero-division handling."""
    if isinstance(rows_or_matrix, dict):
        matrix = rows_or_matrix
    else:
        matrix = confusion_matrix(rows_or_matrix)

    tp = matrix["true_positives"]
    fp = matrix["false_positives"]
    tn = matrix["true_negatives"]
    fn = matrix["false_negatives"]

    positives = tp + fn
    negatives = tn + fp
    predicted = tp + fp
    total = positives + negatives

    recall = tp / positives if positives else 0.0
    false_positive_rate = fp / negatives if negatives else 0.0
    precision = tp / predicted if predicted else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0

    return {
        **matrix,
        "recall": recall,
        "false_positive_rate": false_positive_rate,
        "precision": precision,
        "f1": f1,
        "total_records": total,
        "total_labelled_anomalies": positives,
        "total_predicted_anomalies": predicted,
    }


def threshold_sensitivity(rows, thresholds=DEFAULT_THRESHOLDS):
    """Evaluate precision/recall/F1/FPR over alternate score thresholds."""
    results = []
    for threshold in thresholds:
        adjusted = []
        for row in rows:
            score = row.get("score")
            adjusted.append(
                {
                    **row,
                    "predicted_anomaly": score is not None and score >= threshold,
                }
            )
        result = metrics(adjusted)
        results.append(
            {
                "threshold": threshold,
                "precision": result["precision"],
                "recall": result["recall"],
                "f1": result["f1"],
                "false_positive_rate": result["false_positive_rate"],
                "predicted_anomaly_count": result["total_predicted_anomalies"],
            }
        )
    return results
