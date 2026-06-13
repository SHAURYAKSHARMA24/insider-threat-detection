"""Labelled scenario evaluation for the detector (Phase 9, Objective 4).

This module compares detector predictions with ground-truth labels row by row.
It deliberately performs no ingestion and no anomaly storage: scenario CSV rows
are scored in memory against the existing persisted per-user baselines.

Run as a command to reproduce the published metrics and save them as evidence:

    python -m app.evaluation

This writes ``evidence/metrics.json`` (machine-readable) and
``evidence/evaluation_output.txt`` (the printed report) so the numbers in
``docs/evaluation-report.md`` are generated, not hand-transcribed.
"""
import json
from pathlib import Path

from app.anomalies import classify_severity
from app.config import Config
from app.db import connect
from app.ingest import load_csv, validate_rows
from app.scoring import score_record

LABEL_ANOMALOUS = "anomalous"
DEFAULT_THRESHOLDS = (2.0, 2.5, 3.0, 3.5, 4.0)

# Labelled Objective 4 scenarios, evaluated together for the combined metrics.
SCENARIO_FILENAMES = (
    "scenario_normal.csv",
    "scenario_after_hours.csv",
    "scenario_exfiltration.csv",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
EVIDENCE_DIR = PROJECT_ROOT / "evidence"


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


def evaluate_all(db_path=None, threshold=None, scenario_dir=None):
    """Run every labelled scenario and return per-scenario + combined results.

    Args:
        db_path: SQLite database with the ``Baselines`` table. Defaults to
            :attr:`app.config.Config.DB_PATH`.
        threshold: prediction threshold. Defaults to ``Config.Z_LOW``.
        scenario_dir: directory holding the scenario CSVs. Defaults to ``data/``.

    Returns:
        A JSON-serialisable dict with ``threshold``, ``per_scenario`` (filename
        -> metrics), ``combined`` (metrics over all rows), and
        ``threshold_sensitivity``.
    """
    if db_path is None:
        db_path = Config.DB_PATH
    if threshold is None:
        threshold = Config.Z_LOW
    if scenario_dir is None:
        scenario_dir = DATA_DIR

    per_scenario = {}
    combined_rows = []
    for filename in SCENARIO_FILENAMES:
        rows = run_scenario(Path(scenario_dir) / filename, db_path=db_path, threshold=threshold)
        combined_rows.extend(rows)
        per_scenario[filename] = metrics(rows)

    return {
        "threshold": threshold,
        "per_scenario": per_scenario,
        "combined": metrics(combined_rows),
        "threshold_sensitivity": threshold_sensitivity(combined_rows),
    }


def format_report(results):
    """Render :func:`evaluate_all` output as a plain-text report for evidence."""
    lines = []
    lines.append("Insider Threat Detection -- Labelled Scenario Evaluation")
    lines.append(f"Prediction threshold: {results['threshold']}")
    lines.append("")
    lines.append("Per-scenario results")
    header = f"{'scenario':<28}{'TP':>4}{'FP':>4}{'TN':>5}{'FN':>4}{'Prec':>9}{'Rec':>8}{'F1':>8}{'FPR':>8}"
    lines.append(header)
    lines.append("-" * len(header))
    for name, m in results["per_scenario"].items():
        lines.append(
            f"{name:<28}{m['true_positives']:>4}{m['false_positives']:>4}"
            f"{m['true_negatives']:>5}{m['false_negatives']:>4}"
            f"{m['precision']:>9.4f}{m['recall']:>8.4f}{m['f1']:>8.4f}"
            f"{m['false_positive_rate']:>8.4f}"
        )

    c = results["combined"]
    lines.append("")
    lines.append("Combined results")
    lines.append(
        f"  records={c['total_records']}  labelled_anomalies={c['total_labelled_anomalies']}"
        f"  predicted_anomalies={c['total_predicted_anomalies']}"
    )
    lines.append(
        f"  precision={c['precision']:.4f}  recall={c['recall']:.4f}"
        f"  f1={c['f1']:.4f}  false_positive_rate={c['false_positive_rate']:.4f}"
    )

    lines.append("")
    lines.append("Threshold sensitivity")
    th_header = f"{'threshold':>10}{'Prec':>9}{'Rec':>8}{'F1':>8}{'FPR':>8}{'predicted':>11}"
    lines.append(th_header)
    lines.append("-" * len(th_header))
    for row in results["threshold_sensitivity"]:
        lines.append(
            f"{row['threshold']:>10.1f}{row['precision']:>9.4f}{row['recall']:>8.4f}"
            f"{row['f1']:>8.4f}{row['false_positive_rate']:>8.4f}"
            f"{row['predicted_anomaly_count']:>11}"
        )
    return "\n".join(lines)


def main(db_path=None, evidence_dir=None):
    """Run the full labelled evaluation, print it, and save evidence files."""
    if evidence_dir is None:
        evidence_dir = EVIDENCE_DIR
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    results = evaluate_all(db_path=db_path)
    report = format_report(results)
    print(report)

    (evidence_dir / "metrics.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    (evidence_dir / "evaluation_output.txt").write_text(report + "\n", encoding="utf-8")
    print(f"\nSaved evidence to {evidence_dir / 'metrics.json'} and "
          f"{evidence_dir / 'evaluation_output.txt'}")
    return results


if __name__ == "__main__":
    main()
