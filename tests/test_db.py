"""Phase 2 tests: the SQLite data layer (schema init + connection management).

All tests use a throwaway database under pytest's ``tmp_path`` so no real
database file is touched.
"""
import sqlite3

import pytest

from app import create_app
from app.config import TestingConfig
from app.db import close_db, connect, get_db, init_db

EXPECTED_TABLES = {"Users", "ActivityLogs", "Baselines", "Anomalies"}


@pytest.fixture
def db_path(tmp_path):
    """Return a path to a freshly-initialised temporary database."""
    path = tmp_path / "itd_test.sqlite"
    init_db(str(path))
    return str(path)


def _add_user(conn, user_id="U001", name="user001", role="HR"):
    conn.execute(
        "INSERT INTO Users (user_id, user_name, user_role) VALUES (?, ?, ?)",
        (user_id, name, role),
    )
    conn.commit()


def _add_log(conn, user_id="U001", date="2025-01-01", login="09:00", access=10,
             resource="HR"):
    cur = conn.execute(
        "INSERT INTO ActivityLogs "
        "(user_id, login_time, access_count, resource_type, activity_date) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, login, access, resource, date),
    )
    conn.commit()
    return cur.lastrowid


def test_init_db_creates_all_tables(db_path):
    conn = connect(db_path)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {row["name"] for row in rows}
    conn.close()
    assert EXPECTED_TABLES <= names


def test_connection_has_foreign_keys_enabled(db_path):
    conn = connect(db_path)
    enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.close()
    assert enabled == 1


def test_foreign_key_violation_is_rejected(db_path):
    conn = connect(db_path)
    # Inserting an activity log for a non-existent user must fail (FK enforced).
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO ActivityLogs "
            "(user_id, login_time, access_count, resource_type, activity_date) "
            "VALUES (?, ?, ?, ?, ?)",
            ("GHOST", "09:00", 10, "HR", "2025-01-01"),
        )
        conn.commit()
    conn.close()


def test_insert_and_select_round_trip(db_path):
    conn = connect(db_path)
    _add_user(conn)
    log_id = _add_log(conn, access=42, resource="Finance")

    row = conn.execute(
        "SELECT user_id, access_count, resource_type FROM ActivityLogs WHERE log_id=?",
        (log_id,),
    ).fetchone()
    conn.close()

    assert row["user_id"] == "U001"
    assert row["access_count"] == 42
    assert row["resource_type"] == "Finance"


def test_retrieve_by_user_and_date_range(db_path):
    """FR2: records must be retrievable by user and by date range."""
    conn = connect(db_path)
    _add_user(conn, "U001")
    _add_user(conn, "U002")
    _add_log(conn, "U001", "2025-01-01")
    _add_log(conn, "U001", "2025-01-10")
    _add_log(conn, "U001", "2025-02-01")  # outside the range below
    _add_log(conn, "U002", "2025-01-05")  # different user

    rows = conn.execute(
        "SELECT log_id FROM ActivityLogs "
        "WHERE user_id = ? AND activity_date BETWEEN ? AND ?",
        ("U001", "2025-01-01", "2025-01-31"),
    ).fetchall()
    conn.close()

    assert len(rows) == 2  # only U001's two January records


def test_baseline_and_anomaly_round_trip(db_path):
    """Baselines and Anomalies persist, including FK-linked anomaly rows."""
    conn = connect(db_path)
    _add_user(conn)
    log_id = _add_log(conn)

    conn.execute(
        "INSERT INTO Baselines "
        "(user_id, average_login_time, sd_login_time, average_access_count, "
        " sd_access_count, common_resource_type, resource_distribution_json, "
        " baseline_period) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("U001", 9.0, 0.8, 20.0, 5.0, "HR", '{"HR": 0.6, "General": 0.4}', "2025-01"),
    )
    conn.execute(
        "INSERT INTO Anomalies "
        "(user_id, log_id, deviation_score, severity_level, anomaly_reason, "
        " detection_timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        ("U001", log_id, 3.2, "Medium", "Abnormal login time, Z = 3.2",
         "2025-06-13T10:00:00"),
    )
    conn.commit()

    baseline = conn.execute(
        "SELECT resource_distribution_json FROM Baselines WHERE user_id=?", ("U001",)
    ).fetchone()
    anomaly = conn.execute(
        "SELECT severity_level, anomaly_reason FROM Anomalies WHERE user_id=?", ("U001",)
    ).fetchone()
    conn.close()

    assert baseline["resource_distribution_json"] == '{"HR": 0.6, "General": 0.4}'
    assert anomaly["severity_level"] == "Medium"
    assert "Z = 3.2" in anomaly["anomaly_reason"]


def test_get_db_within_app_context(tmp_path):
    """get_db returns a cached connection inside a Flask app context."""
    app = create_app(TestingConfig)
    app.config["DB_PATH"] = str(tmp_path / "app_ctx.sqlite")

    with app.app_context():
        init_db()  # uses current_app.config["DB_PATH"]
        first = get_db()
        second = get_db()
        assert first is second  # cached on g for the request
        # The connection is usable against the initialised schema.
        count = first.execute("SELECT COUNT(*) FROM Users").fetchone()[0]
        assert count == 0
        close_db()
