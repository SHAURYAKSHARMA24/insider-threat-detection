"""Phase 9 tests: labelled scenario evaluation."""
from pathlib import Path

import pytest

from app.anomalies import process_unscored_activity
from app.baseline import build_baselines
from app.db import connect, init_db
from app.evaluation import confusion_matrix, metrics, run_scenario, threshold_sensitivity
from app.ingest import ingest_activity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_CSV = PROJECT_ROOT / "data" / "activity_baseline.csv"
AFTER_HOURS_CSV = PROJECT_ROOT / "data" / "scenario_after_hours.csv"

HEADER = "user_id,user_name,user_role,activity_date,login_time,access_count,resource_type,label\n"


def _write_csv(tmp_path, *rows, name="scenario.csv"):
    path = tmp_path / name
    path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return str(path)


def _controlled_db(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    init_db(db_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO Users (user_id, user_name, user_role) VALUES (?, ?, ?)",
        ("U001", "user001", "HR"),
    )
    conn.execute(
        "INSERT INTO Baselines "
        "(user_id, average_login_time, sd_login_time, average_access_count, "
        " sd_access_count, common_resource_type, resource_distribution_json, baseline_period) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("U001", 9.0, 1.0, 20.0, 5.0, "HR", '{"HR": 1.0}', "2025-01-01 to 2025-01-31"),
    )
    conn.commit()
    conn.close()
    return db_path


def test_confusion_matrix_counts_all_outcomes():
    rows = [
        {"actual_anomaly": True, "predicted_anomaly": True},
        {"actual_anomaly": False, "predicted_anomaly": True},
        {"actual_anomaly": False, "predicted_anomaly": False},
        {"actual_anomaly": True, "predicted_anomaly": False},
    ]

    assert confusion_matrix(rows) == {
        "true_positives": 1,
        "false_positives": 1,
        "true_negatives": 1,
        "false_negatives": 1,
    }


def test_metrics_calculates_rates_and_totals():
    result = metrics(
        {
            "true_positives": 8,
            "false_positives": 2,
            "true_negatives": 18,
            "false_negatives": 2,
        }
    )

    assert result["recall"] == pytest.approx(0.8)
    assert result["false_positive_rate"] == pytest.approx(0.1)
    assert result["precision"] == pytest.approx(0.8)
    assert result["f1"] == pytest.approx(0.8)
    assert result["total_records"] == 30
    assert result["total_labelled_anomalies"] == 10
    assert result["total_predicted_anomalies"] == 10


def test_metrics_handles_zero_division_cases():
    no_positives = metrics(
        {
            "true_positives": 0,
            "false_positives": 0,
            "true_negatives": 5,
            "false_negatives": 0,
        }
    )
    no_predictions = metrics(
        {
            "true_positives": 0,
            "false_positives": 0,
            "true_negatives": 3,
            "false_negatives": 2,
        }
    )

    assert no_positives["recall"] == 0.0
    assert no_positives["precision"] == 0.0
    assert no_positives["f1"] == 0.0
    assert no_predictions["precision"] == 0.0
    assert no_predictions["f1"] == 0.0


def test_run_scenario_scores_labelled_fixture_row_by_row(tmp_path):
    db_path = _controlled_db(tmp_path)
    scenario = _write_csv(
        tmp_path,
        "U001,user001,HR,2025-05-01,09:00,20,HR,normal\n",
        "U001,user001,HR,2025-05-02,12:00,20,HR,anomalous\n",
    )

    rows = run_scenario(scenario, db_path=db_path)

    assert len(rows) == 2
    assert rows[0]["actual_anomaly"] is False
    assert rows[0]["predicted_anomaly"] is False
    assert rows[0]["score"] == pytest.approx(0.0)
    assert rows[1]["actual_anomaly"] is True
    assert rows[1]["predicted_anomaly"] is True
    assert rows[1]["responsible_feature"] == "login_time"
    assert rows[1]["score"] == pytest.approx(3.0)
    assert rows[1]["severity"] == "Medium"


def test_threshold_sensitivity_returns_one_result_per_threshold(tmp_path):
    db_path = _controlled_db(tmp_path)
    scenario = _write_csv(
        tmp_path,
        "U001,user001,HR,2025-05-01,11:12,20,HR,anomalous\n",
        "U001,user001,HR,2025-05-02,12:00,20,HR,anomalous\n",
    )
    rows = run_scenario(scenario, db_path=db_path)

    results = threshold_sensitivity(rows, thresholds=(2.0, 2.5, 3.0))

    assert [r["threshold"] for r in results] == [2.0, 2.5, 3.0]
    assert all("precision" in r and "recall" in r and "predicted_anomaly_count" in r for r in results)
    assert results[0]["predicted_anomaly_count"] >= results[-1]["predicted_anomaly_count"]


def test_evaluation_does_not_mutate_existing_anomaly_store(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    ingest_activity(str(BASELINE_CSV), db_path=db_path)
    build_baselines(db_path=db_path)
    ingest_activity(str(AFTER_HOURS_CSV), db_path=db_path)
    process_unscored_activity(db_path=db_path, clear_existing=True)

    conn = connect(db_path)
    before = conn.execute("SELECT COUNT(*) FROM Anomalies").fetchone()[0]
    conn.close()

    rows = run_scenario(str(AFTER_HOURS_CSV), db_path=db_path)
    assert rows

    conn = connect(db_path)
    after = conn.execute("SELECT COUNT(*) FROM Anomalies").fetchone()[0]
    conn.close()

    assert after == before
