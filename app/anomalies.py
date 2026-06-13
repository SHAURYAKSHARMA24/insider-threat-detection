"""Anomaly storage and severity labelling (Phase 6, FR5 / FR6).

This module turns Phase 5 deviation scores into stored, severity-labelled
anomalies. It bridges the pure scoring logic (``app.scoring``) and the database
(``app.db``):

* :func:`classify_severity` maps a deviation score to exactly one severity band
  (or ``None`` below threshold / for non-finite scores).
* :func:`flag_and_store` scores a single record and persists it only if flagged.
* :func:`process_unscored_activity` batch-scores existing ``ActivityLogs`` rows
  against each user's latest baseline and stores the flagged ones.

Severity bands are taken from configuration (FR5 -- thresholds are configurable):
    Low:    Z_LOW    <= score < Z_MEDIUM   (default 2.5 .. <3.0)
    Medium: Z_MEDIUM <= score < Z_HIGH     (default 3.0 .. <4.0)
    High:   score >= Z_HIGH                (default >= 4.0)
"""
import math
from datetime import datetime

from app.config import Config
from app.db import connect
from app.scoring import score_record

SEVERITY_LEVELS = ("Low", "Medium", "High")


def classify_severity(score):
    """Return the severity band for a deviation score, or ``None``.

    Returns ``None`` for scores below ``Z_LOW`` and for invalid/non-finite
    values (NaN, inf, wrong type) so such scores are never stored. Otherwise
    returns exactly one of ``"Low"``, ``"Medium"``, ``"High"`` (FR6).
    """
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    if not math.isfinite(score):
        return None
    if score < Config.Z_LOW:
        return None
    if score < Config.Z_MEDIUM:
        return "Low"
    if score < Config.Z_HIGH:
        return "Medium"
    return "High"


def _insert_anomaly(conn, user_id, log_id, deviation_score, severity_level, reason):
    """Insert one anomaly row (parameterised) and return its new id."""
    cursor = conn.execute(
        "INSERT INTO Anomalies "
        "(user_id, log_id, deviation_score, severity_level, anomaly_reason, "
        " detection_timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (
            user_id,
            log_id,
            deviation_score,
            severity_level,
            reason,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    return cursor.lastrowid


def flag_and_store(record, baseline, db_path=None):
    """Score one record and store it as an anomaly only if it is flagged.

    Args:
        record: mapping with ``user_id``, ``log_id`` (for the foreign keys),
            plus ``login_time``, ``access_count``, ``resource_type`` for scoring.
        baseline: the user's baseline mapping (see :func:`app.scoring.score_record`).
        db_path: target database; defaults to ``Config.DB_PATH``.

    Returns:
        A dict: ``flagged`` (bool), ``deviation_score``, ``severity_level``
        (``None`` if not flagged), ``anomaly_reason``, and ``anomaly_id``
        (``None`` unless a row was inserted).
    """
    if db_path is None:
        db_path = Config.DB_PATH

    scored = score_record(record, baseline)
    deviation_score = scored["deviation_score"]
    severity_level = classify_severity(deviation_score)

    result = {
        "flagged": False,
        "deviation_score": deviation_score,
        "severity_level": severity_level,
        "anomaly_reason": scored["reason"],
        "anomaly_id": None,
    }
    if severity_level is None:
        return result

    conn = connect(db_path)
    try:
        anomaly_id = _insert_anomaly(
            conn, record["user_id"], record["log_id"], deviation_score,
            severity_level, scored["reason"],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    result["flagged"] = True
    result["anomaly_id"] = anomaly_id
    return result


def _load_latest_baselines(conn):
    """Return ``{user_id: baseline_dict}`` using each user's newest baseline."""
    rows = conn.execute(
        "SELECT b.* FROM Baselines b "
        "JOIN (SELECT user_id, MAX(baseline_id) AS latest FROM Baselines GROUP BY user_id) m "
        "ON b.baseline_id = m.latest"
    ).fetchall()
    return {row["user_id"]: dict(row) for row in rows}


def process_unscored_activity(db_path=None, clear_existing=False):
    """Score every ``ActivityLogs`` row against its user's baseline and store anomalies.

    Args:
        db_path: target database; defaults to ``Config.DB_PATH``.
        clear_existing: when True, delete existing ``Anomalies`` rows first so
            repeated demo runs do not accumulate duplicates.

    Returns:
        A summary dict: ``records_scored``, ``anomalies_created``,
        ``severity_counts`` (``{Low, Medium, High}``), and
        ``skipped_no_baseline`` (logs whose user has no baseline).
    """
    if db_path is None:
        db_path = Config.DB_PATH

    records_scored = 0
    skipped_no_baseline = 0
    severity_counts = {level: 0 for level in SEVERITY_LEVELS}
    pending = []

    conn = connect(db_path)
    try:
        if clear_existing:
            conn.execute("DELETE FROM Anomalies")

        baselines = _load_latest_baselines(conn)
        logs = conn.execute(
            "SELECT log_id, user_id, login_time, access_count, resource_type "
            "FROM ActivityLogs"
        ).fetchall()

        for log in logs:
            baseline = baselines.get(log["user_id"])
            if baseline is None:
                skipped_no_baseline += 1
                continue
            records_scored += 1
            scored = score_record(dict(log), baseline)
            severity_level = classify_severity(scored["deviation_score"])
            if severity_level is None:
                continue
            pending.append(
                (log["user_id"], log["log_id"], scored["deviation_score"],
                 severity_level, scored["reason"],
                 datetime.now().isoformat(timespec="seconds"))
            )
            severity_counts[severity_level] += 1

        if pending:
            conn.executemany(
                "INSERT INTO Anomalies "
                "(user_id, log_id, deviation_score, severity_level, anomaly_reason, "
                " detection_timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                pending,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "records_scored": records_scored,
        "anomalies_created": len(pending),
        "severity_counts": severity_counts,
        "skipped_no_baseline": skipped_no_baseline,
    }


def main():
    """Process all activity in the configured database and print a summary."""
    summary = process_unscored_activity(clear_existing=True)
    print("Anomaly processing summary:")
    print(f"  records_scored:      {summary['records_scored']}")
    print(f"  anomalies_created:   {summary['anomalies_created']}")
    print(f"  severity_counts:     {summary['severity_counts']}")
    print(f"  skipped_no_baseline: {summary['skipped_no_baseline']}")


if __name__ == "__main__":
    main()
