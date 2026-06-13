"""Tests for the labelled-evaluation command (``python -m app.evaluation``).

These cover the Phase B reporting layer: ``evaluate_all`` aggregates the three
labelled scenarios, and ``main`` saves the generated evidence files so the
numbers in ``docs/evaluation-report.md`` are reproducible, not transcribed.
"""
import json
from pathlib import Path

from app.baseline import build_baselines
from app.evaluation import evaluate_all, format_report, main
from app.ingest import ingest_activity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
BASELINE_CSV = DATA_DIR / "activity_baseline.csv"

SCENARIO_KEYS = {
    "scenario_normal.csv",
    "scenario_after_hours.csv",
    "scenario_exfiltration.csv",
}


def _baseline_db(tmp_path):
    """Build a temporary database with ingested activity and per-user baselines."""
    db_path = str(tmp_path / "itd.sqlite")
    ingest_activity(str(BASELINE_CSV), db_path=db_path)
    build_baselines(db_path=db_path)
    return db_path


def test_evaluate_all_aggregates_scenarios(tmp_path):
    db_path = _baseline_db(tmp_path)
    results = evaluate_all(db_path=db_path)

    assert set(results) == {"threshold", "per_scenario", "combined", "threshold_sensitivity"}
    assert set(results["per_scenario"]) == SCENARIO_KEYS

    combined = results["combined"]
    # Deterministic dataset: 210 rows, 56 labelled anomalies across the scenarios.
    assert combined["total_records"] == 210
    assert combined["total_labelled_anomalies"] == 56
    # Detector is strong at the default threshold.
    assert combined["precision"] > 0.9
    assert combined["recall"] > 0.85


def test_threshold_sensitivity_is_monotonic_in_predictions(tmp_path):
    db_path = _baseline_db(tmp_path)
    results = evaluate_all(db_path=db_path)
    counts = [row["predicted_anomaly_count"] for row in results["threshold_sensitivity"]]
    # Raising the threshold never increases the number of predicted anomalies.
    assert counts == sorted(counts, reverse=True)


def test_main_writes_evidence_files(tmp_path):
    db_path = _baseline_db(tmp_path)
    evidence_dir = tmp_path / "evidence"

    results = main(db_path=db_path, evidence_dir=evidence_dir)

    metrics_file = evidence_dir / "metrics.json"
    report_file = evidence_dir / "evaluation_output.txt"
    assert metrics_file.exists()
    assert report_file.exists()

    saved = json.loads(metrics_file.read_text(encoding="utf-8"))
    assert saved["combined"]["total_records"] == results["combined"]["total_records"]
    assert "Combined results" in report_file.read_text(encoding="utf-8")


def test_format_report_is_plain_text(tmp_path):
    db_path = _baseline_db(tmp_path)
    report = format_report(evaluate_all(db_path=db_path))
    assert "Per-scenario results" in report
    assert "Threshold sensitivity" in report
