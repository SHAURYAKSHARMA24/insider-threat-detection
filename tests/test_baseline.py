"""Phase 4 tests: per-user baseline generation (FR3 / Objective 2)."""
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.config import Config
from app.db import connect, init_db
from app.baseline import build_baselines, compute_user_baseline, login_time_to_hours
from app.ingest import ingest_activity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_CSV = PROJECT_ROOT / "data" / "activity_baseline.csv"


def _seed_user_logs(conn, user_id, n, login="09:00", access=10, resource="HR",
                    start="2025-01-01"):
    conn.execute(
        "INSERT OR IGNORE INTO Users (user_id, user_name, user_role) VALUES (?, ?, ?)",
        (user_id, user_id.lower(), "HR"),
    )
    base = date.fromisoformat(start)
    for i in range(n):
        conn.execute(
            "INSERT INTO ActivityLogs "
            "(user_id, login_time, access_count, resource_type, activity_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, login, access, resource, (base + timedelta(days=i)).isoformat()),
        )
    conn.commit()


# --------------------------------------------------------------------------- #
# 1. login_time_to_hours
# --------------------------------------------------------------------------- #
def test_login_time_to_hours_basic():
    assert login_time_to_hours("09:30") == 9.5
    assert login_time_to_hours("00:00") == 0.0
    assert login_time_to_hours("23:59") == pytest.approx(23 + 59 / 60)


@pytest.mark.parametrize("bad", ["9", "25:00", "09:60", "ab:cd", "0930", "", "12:5a"])
def test_login_time_to_hours_invalid_raises(bad):
    with pytest.raises(ValueError):
        login_time_to_hours(bad)


# --------------------------------------------------------------------------- #
# 2. Known-fixture baseline correctness
# --------------------------------------------------------------------------- #
def test_compute_user_baseline_known_values():
    rows = [
        {"login_time": "08:00", "access_count": 10, "resource_type": "HR",
         "activity_date": "2025-01-01"},
        {"login_time": "10:00", "access_count": 20, "resource_type": "HR",
         "activity_date": "2025-01-03"},
        {"login_time": "09:00", "access_count": 30, "resource_type": "General",
         "activity_date": "2025-01-02"},
    ]
    b = compute_user_baseline(rows)

    assert b["average_login_time"] == pytest.approx(9.0)
    assert b["sd_login_time"] == pytest.approx(math.sqrt(2 / 3))      # population SD
    assert b["average_access_count"] == pytest.approx(20.0)
    assert b["sd_access_count"] == pytest.approx(math.sqrt(200 / 3))
    assert b["common_resource_type"] == "HR"
    assert b["baseline_period"] == "2025-01-01 to 2025-01-03"

    distribution = json.loads(b["resource_distribution_json"])
    assert distribution["HR"] == pytest.approx(2 / 3)
    assert distribution["General"] == pytest.approx(1 / 3)


# --------------------------------------------------------------------------- #
# 3. Minimum-record gate
# --------------------------------------------------------------------------- #
def test_minimum_record_gate_excludes_19_includes_20(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    init_db(db_path)
    conn = connect(db_path)
    _seed_user_logs(conn, "UA", 20)   # eligible
    _seed_user_logs(conn, "UB", 19)   # excluded
    conn.close()

    summary = build_baselines(db_path=db_path)

    assert summary["eligible_users"] == 1
    assert summary["baselines_created"] == 1
    excluded_ids = {e["user_id"] for e in summary["excluded_users"]}
    assert excluded_ids == {"UB"}
    excluded_b = next(e for e in summary["excluded_users"] if e["user_id"] == "UB")
    assert excluded_b["record_count"] == 19
    assert "20" in excluded_b["reason"]

    conn = connect(db_path)
    baseline_users = {r["user_id"] for r in conn.execute("SELECT user_id FROM Baselines")}
    conn.close()
    assert baseline_users == {"UA"}


# --------------------------------------------------------------------------- #
# 4. SD = 0 guard
# --------------------------------------------------------------------------- #
def test_constant_values_give_zero_sd():
    rows = [
        {"login_time": "09:00", "access_count": 10, "resource_type": "HR",
         "activity_date": f"2025-01-{i + 1:02d}"}
        for i in range(20)
    ]
    b = compute_user_baseline(rows)
    assert b["sd_login_time"] == 0.0
    assert b["sd_access_count"] == 0.0
    assert b["average_login_time"] == pytest.approx(9.0)
    assert b["average_access_count"] == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# 5. Database write + no duplication on re-run
# --------------------------------------------------------------------------- #
def test_build_baselines_writes_and_does_not_duplicate(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    init_db(db_path)
    conn = connect(db_path)
    _seed_user_logs(conn, "UA", 25)
    conn.close()

    build_baselines(db_path=db_path, clear_existing=True)
    build_baselines(db_path=db_path, clear_existing=True)  # rebuild

    conn = connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM Baselines").fetchone()[0]
    # FK integrity: baseline's user exists in Users.
    orphans = conn.execute(
        "SELECT COUNT(*) FROM Baselines b LEFT JOIN Users u ON b.user_id = u.user_id "
        "WHERE u.user_id IS NULL"
    ).fetchone()[0]
    conn.close()

    assert count == 1   # not duplicated by the second run
    assert orphans == 0


# --------------------------------------------------------------------------- #
# 6. Real dataset integration
# --------------------------------------------------------------------------- #
def test_real_dataset_produces_20_complete_baselines(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    ingest_activity(str(BASELINE_CSV), db_path=db_path)

    summary = build_baselines(db_path=db_path)
    assert summary["baselines_created"] == 20

    conn = connect(db_path)
    rows = conn.execute(
        "SELECT user_id, average_login_time, sd_login_time, average_access_count, "
        "sd_access_count, common_resource_type, resource_distribution_json "
        "FROM Baselines"
    ).fetchall()
    conn.close()

    assert len(rows) == 20
    for r in rows:
        assert r["average_login_time"] is not None
        assert r["sd_login_time"] is not None
        assert r["average_access_count"] is not None
        assert r["sd_access_count"] is not None
        assert r["common_resource_type"]
        distribution = json.loads(r["resource_distribution_json"])  # valid JSON
        assert abs(sum(distribution.values()) - 1.0) < 1e-9        # proportions sum to 1
