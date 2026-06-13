"""Phase 6 tests: anomaly storage and severity labelling (FR5 / FR6)."""
import math
from pathlib import Path

import pytest

from app.anomalies import classify_severity, flag_and_store, process_unscored_activity
from app.baseline import build_baselines
from app.db import connect, init_db
from app.ingest import ingest_activity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_CSV = PROJECT_ROOT / "data" / "activity_baseline.csv"
AFTER_HOURS_CSV = PROJECT_ROOT / "data" / "scenario_after_hours.csv"

# In-memory baseline used by single-record tests.
BASE = {
    "average_login_time": 9.0,
    "sd_login_time": 1.0,
    "average_access_count": 20.0,
    "sd_access_count": 5.0,
    "resource_distribution_json": '{"HR": 1.0}',
}


def _add_user_and_log(conn, user_id="U001", login="09:00", access=20, resource="HR"):
    conn.execute(
        "INSERT OR IGNORE INTO Users (user_id, user_name, user_role) VALUES (?, ?, ?)",
        (user_id, user_id.lower(), "HR"),
    )
    cur = conn.execute(
        "INSERT INTO ActivityLogs "
        "(user_id, login_time, access_count, resource_type, activity_date) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, login, access, resource, "2025-01-01"),
    )
    conn.commit()
    return cur.lastrowid


# --------------------------------------------------------------------------- #
# 1. Severity band edges
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "score, expected",
    [
        (2.4, None),
        (2.5, "Low"),
        (2.99, "Low"),
        (3.0, "Medium"),
        (3.99, "Medium"),
        (4.0, "High"),
        (12.5, "High"),
        (999.0, "High"),
    ],
)
def test_classify_severity_bands(score, expected):
    assert classify_severity(score) == expected


# --------------------------------------------------------------------------- #
# 2. Invalid scores
# --------------------------------------------------------------------------- #
def test_classify_severity_invalid_and_negative_return_none():
    assert classify_severity(float("nan")) is None
    assert classify_severity(float("inf")) is None
    assert classify_severity(-1.0) is None     # negative is never flagged
    assert classify_severity(None) is None
    assert classify_severity("x") is None
    assert classify_severity(True) is None


def test_non_finite_scores_are_not_stored(tmp_path):
    """A NaN/inf score must not produce a stored anomaly."""
    db_path = str(tmp_path / "itd.sqlite")
    init_db(db_path)
    conn = connect(db_path)
    log_id = _add_user_and_log(conn)
    conn.close()

    # sd=0 with an equal value yields deviation 0.0 -> not flagged; a constant
    # baseline cannot emit NaN/inf, so we assert classify_severity blocks them.
    assert classify_severity(math.inf) is None
    assert classify_severity(math.nan) is None

    record = {"user_id": "U001", "log_id": log_id, "login_time": "09:00",
              "access_count": 20, "resource_type": "HR"}
    base_constant = {"average_login_time": 9.0, "sd_login_time": 0.0,
                     "average_access_count": 20.0, "sd_access_count": 0.0,
                     "resource_distribution_json": '{"HR": 1.0}'}
    result = flag_and_store(record, base_constant, db_path=db_path)
    assert result["flagged"] is False

    conn = connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM Anomalies").fetchone()[0]
    conn.close()
    assert count == 0


# --------------------------------------------------------------------------- #
# 3. Single-record storage
# --------------------------------------------------------------------------- #
def test_below_threshold_record_not_stored(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    init_db(db_path)
    conn = connect(db_path)
    log_id = _add_user_and_log(conn)
    conn.close()

    record = {"user_id": "U001", "log_id": log_id, "login_time": "09:00",
              "access_count": 20, "resource_type": "HR"}
    result = flag_and_store(record, BASE, db_path=db_path)

    assert result["flagged"] is False
    assert result["severity_level"] is None
    assert result["anomaly_id"] is None

    conn = connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM Anomalies").fetchone()[0] == 0
    conn.close()


def test_anomalous_record_is_stored_with_correct_fields(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    init_db(db_path)
    conn = connect(db_path)
    log_id = _add_user_and_log(conn, login="03:00")  # after-hours log row
    conn.close()

    record = {"user_id": "U001", "log_id": log_id, "login_time": "03:00",
              "access_count": 20, "resource_type": "HR"}
    result = flag_and_store(record, BASE, db_path=db_path)

    assert result["flagged"] is True
    assert result["severity_level"] == "High"      # |3-9|/1 = 6.0
    assert result["deviation_score"] == pytest.approx(6.0)
    assert result["anomaly_id"] is not None

    conn = connect(db_path)
    row = conn.execute(
        "SELECT * FROM Anomalies WHERE anomaly_id = ?", (result["anomaly_id"],)
    ).fetchone()
    conn.close()

    assert row["user_id"] == "U001"
    assert row["log_id"] == log_id
    assert row["deviation_score"] == pytest.approx(6.0)
    assert row["severity_level"] == "High"
    assert "login_time" in row["anomaly_reason"]
    assert row["detection_timestamp"]  # non-empty timestamp


# --------------------------------------------------------------------------- #
# 4. Batch processing
# --------------------------------------------------------------------------- #
def test_batch_processing_creates_and_counts_anomalies(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    ingest_activity(str(BASELINE_CSV), db_path=db_path)
    build_baselines(db_path=db_path)
    ingest_activity(str(AFTER_HOURS_CSV), db_path=db_path)

    conn = connect(db_path)
    before = conn.execute("SELECT COUNT(*) FROM Anomalies").fetchone()[0]
    total_logs = conn.execute("SELECT COUNT(*) FROM ActivityLogs").fetchone()[0]
    conn.close()
    assert before == 0

    summary = process_unscored_activity(db_path=db_path, clear_existing=True)

    conn = connect(db_path)
    after = conn.execute("SELECT COUNT(*) FROM Anomalies").fetchone()[0]
    conn.close()

    assert summary["anomalies_created"] > 0
    assert after == summary["anomalies_created"]
    assert after > before
    assert summary["records_scored"] == total_logs
    assert summary["skipped_no_baseline"] == 0
    # Severity counts must add up to the number of anomalies created.
    assert sum(summary["severity_counts"].values()) == summary["anomalies_created"]


def test_skipped_no_baseline_counted(tmp_path):
    """Logs for a user with no baseline are skipped, not flagged."""
    db_path = str(tmp_path / "itd.sqlite")
    init_db(db_path)
    conn = connect(db_path)
    _add_user_and_log(conn, "UX", login="03:00")  # no baseline built for UX
    conn.close()

    summary = process_unscored_activity(db_path=db_path, clear_existing=True)
    assert summary["skipped_no_baseline"] == 1
    assert summary["records_scored"] == 0
    assert summary["anomalies_created"] == 0


# --------------------------------------------------------------------------- #
# 5. Re-run behaviour
# --------------------------------------------------------------------------- #
def test_rerun_clear_existing_prevents_duplicates(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    ingest_activity(str(BASELINE_CSV), db_path=db_path)
    build_baselines(db_path=db_path)
    ingest_activity(str(AFTER_HOURS_CSV), db_path=db_path)

    first = process_unscored_activity(db_path=db_path, clear_existing=True)
    second = process_unscored_activity(db_path=db_path, clear_existing=True)

    conn = connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM Anomalies").fetchone()[0]
    conn.close()

    assert second["anomalies_created"] == first["anomalies_created"]
    assert count == first["anomalies_created"]  # not doubled


# --------------------------------------------------------------------------- #
# 6. Foreign-key integrity
# --------------------------------------------------------------------------- #
def test_stored_anomalies_reference_valid_rows(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    ingest_activity(str(BASELINE_CSV), db_path=db_path)
    build_baselines(db_path=db_path)
    ingest_activity(str(AFTER_HOURS_CSV), db_path=db_path)
    process_unscored_activity(db_path=db_path, clear_existing=True)

    conn = connect(db_path)
    fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    orphan_users = conn.execute(
        "SELECT COUNT(*) FROM Anomalies a LEFT JOIN Users u ON a.user_id = u.user_id "
        "WHERE u.user_id IS NULL"
    ).fetchone()[0]
    orphan_logs = conn.execute(
        "SELECT COUNT(*) FROM Anomalies a LEFT JOIN ActivityLogs l ON a.log_id = l.log_id "
        "WHERE l.log_id IS NULL"
    ).fetchone()[0]
    conn.close()

    assert fk_on == 1
    assert orphan_users == 0
    assert orphan_logs == 0
