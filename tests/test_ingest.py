"""Phase 3 tests: CSV ingestion with validation (FR1).

Validation tests build tiny CSV files under ``tmp_path``; the happy-path test
ingests the real ``data/activity_baseline.csv``. No production database is
touched -- every ingest targets a temporary database file.
"""
from pathlib import Path

import pytest

from app.db import connect
from app.ingest import ingest_activity, load_csv, validate_rows

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_CSV = PROJECT_ROOT / "data" / "activity_baseline.csv"

HEADER = "user_id,user_name,user_role,activity_date,login_time,access_count,resource_type,label\n"
VALID_ROW = "U001,user001,HR,2025-01-01,09:00,10,HR,normal\n"


def _write_csv(tmp_path, *rows, header=HEADER, name="in.csv"):
    path = tmp_path / name
    path.write_text(header + "".join(rows), encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- #
# 1. Happy path
# --------------------------------------------------------------------------- #
def test_happy_path_ingests_baseline(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    summary = ingest_activity(str(BASELINE_CSV), db_path=db_path)

    conn = connect(db_path)
    log_count = conn.execute("SELECT COUNT(*) FROM ActivityLogs").fetchone()[0]
    user_count = conn.execute("SELECT COUNT(*) FROM Users").fetchone()[0]
    conn.close()

    assert log_count >= 10_000
    assert user_count == 20
    assert summary["rows_ingested"] == log_count
    assert summary["users_inserted_or_seen"] == 20
    assert summary["rows_rejected"] == 0
    assert summary["rows_read"] == summary["rows_ingested"]


# --------------------------------------------------------------------------- #
# 2. Validation
# --------------------------------------------------------------------------- #
def test_bad_login_time_rejected(tmp_path):
    csv = _write_csv(tmp_path, "U001,user001,HR,2025-01-01,25:00,10,HR,normal\n")
    clean, rejected = validate_rows(load_csv(csv))
    assert len(clean) == 0
    assert len(rejected) == 1
    assert "login_time" in rejected.iloc[0]["rejection_reason"]


def test_bad_activity_date_rejected(tmp_path):
    csv = _write_csv(tmp_path, "U001,user001,HR,not-a-date,09:00,10,HR,normal\n")
    clean, rejected = validate_rows(load_csv(csv))
    assert len(clean) == 0
    assert "activity_date" in rejected.iloc[0]["rejection_reason"]


def test_non_positive_access_count_rejected(tmp_path):
    csv = _write_csv(
        tmp_path,
        "U001,user001,HR,2025-01-01,09:00,0,HR,normal\n",
        "U002,user002,HR,2025-01-01,09:00,-5,HR,normal\n",
    )
    clean, rejected = validate_rows(load_csv(csv))
    assert len(clean) == 0
    assert len(rejected) == 2


def test_non_integer_access_count_rejected(tmp_path):
    csv = _write_csv(tmp_path, "U001,user001,HR,2025-01-01,09:00,3.5,HR,normal\n")
    clean, rejected = validate_rows(load_csv(csv))
    assert len(clean) == 0
    assert "access_count" in rejected.iloc[0]["rejection_reason"]


def test_missing_required_column_raises(tmp_path):
    header = "user_id,user_name,user_role,activity_date,login_time,resource_type,label\n"
    csv = _write_csv(tmp_path, "U001,user001,HR,2025-01-01,09:00,HR,normal\n", header=header)
    with pytest.raises(ValueError):
        validate_rows(load_csv(csv))


def test_empty_csv_returns_zero_ingested(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    summary = ingest_activity(str(path), db_path=str(tmp_path / "e.sqlite"))
    assert summary["rows_read"] == 0
    assert summary["rows_ingested"] == 0


def test_invalid_label_rejected(tmp_path):
    csv = _write_csv(tmp_path, "U001,user001,HR,2025-01-01,09:00,10,HR,bogus\n")
    clean, rejected = validate_rows(load_csv(csv))
    assert len(clean) == 0
    assert "label" in rejected.iloc[0]["rejection_reason"]


def test_load_csv_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_csv(str(tmp_path / "does_not_exist.csv"))


# --------------------------------------------------------------------------- #
# 3. Database integrity
# --------------------------------------------------------------------------- #
def test_no_orphan_activity_logs(tmp_path):
    """Every ActivityLogs.user_id must exist in Users (users inserted first)."""
    db_path = str(tmp_path / "itd.sqlite")
    ingest_activity(str(BASELINE_CSV), db_path=db_path)
    conn = connect(db_path)
    orphans = conn.execute(
        "SELECT COUNT(*) FROM ActivityLogs a "
        "LEFT JOIN Users u ON a.user_id = u.user_id WHERE u.user_id IS NULL"
    ).fetchone()[0]
    fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.close()
    assert orphans == 0
    assert fk_on == 1


def test_query_by_user_and_date_range_after_ingest(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    csv = _write_csv(
        tmp_path,
        "U001,user001,HR,2025-01-01,09:00,10,HR,normal\n",
        "U001,user001,HR,2025-01-20,09:00,12,HR,normal\n",
        "U001,user001,HR,2025-03-01,09:00,12,HR,normal\n",
        "U002,user002,Finance,2025-01-10,08:30,15,Finance,normal\n",
    )
    ingest_activity(csv, db_path=db_path)
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT log_id FROM ActivityLogs "
        "WHERE user_id = ? AND activity_date BETWEEN ? AND ?",
        ("U001", "2025-01-01", "2025-01-31"),
    ).fetchall()
    conn.close()
    assert len(rows) == 2


# --------------------------------------------------------------------------- #
# 4. Safety
# --------------------------------------------------------------------------- #
def test_rejected_rows_are_not_inserted(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    csv = _write_csv(
        tmp_path,
        VALID_ROW,                                                    # valid -> inserted
        "U002,user002,HR,2025-01-01,25:00,10,HR,normal\n",           # bad login_time -> rejected
    )
    summary = ingest_activity(csv, db_path=db_path)
    conn = connect(db_path)
    log_count = conn.execute("SELECT COUNT(*) FROM ActivityLogs").fetchone()[0]
    u2 = conn.execute("SELECT COUNT(*) FROM Users WHERE user_id='U002'").fetchone()[0]
    conn.close()
    assert summary["rows_ingested"] == 1
    assert summary["rows_rejected"] == 1
    assert log_count == 1
    assert u2 == 0  # rejected row's user was never inserted


def test_sql_injection_attempt_is_stored_literally(tmp_path):
    """Parameterised SQL: a malicious user_id is stored as data, not executed."""
    db_path = str(tmp_path / "itd.sqlite")
    evil = "x'); DROP TABLE Users;--"
    csv = _write_csv(tmp_path, f"{evil},user,HR,2025-01-01,09:00,10,HR,normal\n")
    ingest_activity(csv, db_path=db_path)

    conn = connect(db_path)
    # Users table must still exist (would raise if it had been dropped).
    conn.execute("SELECT COUNT(*) FROM Users").fetchone()
    stored = conn.execute("SELECT user_id FROM Users WHERE user_id = ?", (evil,)).fetchone()
    conn.close()
    assert stored is not None
    assert stored["user_id"] == evil


def test_source_uses_parameterised_sql():
    """Static guard: no string-interpolated SQL in the ingestion module."""
    src = (PROJECT_ROOT / "app" / "ingest.py").read_text(encoding="utf-8")
    assert 'f"INSERT' not in src and "f'INSERT" not in src
    assert 'f"SELECT' not in src and "f'SELECT" not in src
    assert "VALUES (?" in src
