"""Per-user statistical baseline generation (Phase 4, FR3 / Objective 2).

For every user with at least ``MIN_RECORDS`` activity records, this module
computes a behavioural baseline -- the mean and standard deviation of login
hour and access count, the modal resource type, and the resource-type
distribution -- and writes one row to the ``Baselines`` table. Users below the
record threshold are excluded with an informative log message.

Scope note: this phase produces baselines only. Z-score scoring, severity
labelling, and anomaly storage are implemented in later phases and consume the
baselines written here (including ``resource_distribution_json`` for categorical
rarity scoring).
"""
import json
import logging
from collections import Counter

import numpy as np

from app.config import Config
from app.db import connect, init_db

logger = logging.getLogger(__name__)


def login_time_to_hours(login_time):
    """Convert an ``HH:MM`` string into decimal hours.

    Example: ``"09:30"`` -> ``9.5``.

    Raises:
        ValueError: if the input is not a valid ``HH:MM`` time in 00:00-23:59.
    """
    if not isinstance(login_time, str):
        raise ValueError(f"login_time must be a string 'HH:MM', got {login_time!r}")
    parts = login_time.strip().split(":")
    if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        raise ValueError(f"Invalid login_time format (expected HH:MM): {login_time!r}")
    hours, minutes = int(parts[0]), int(parts[1])
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError(f"login_time out of range (00:00-23:59): {login_time!r}")
    return hours + minutes / 60.0


def compute_user_baseline(rows):
    """Compute a baseline dict from one user's activity rows.

    Args:
        rows: an iterable of mappings (``sqlite3.Row`` or ``dict``) each exposing
            ``login_time``, ``access_count``, ``resource_type``, ``activity_date``.

    Returns:
        A dict with ``average_login_time``, ``sd_login_time``,
        ``average_access_count``, ``sd_access_count``, ``common_resource_type``,
        ``resource_distribution_json`` (JSON of category -> proportion), and
        ``baseline_period`` (``"<min date> to <max date>"``).

    Notes:
        Population standard deviation (``ddof=0``) is used: the baseline
        describes the observed history itself rather than estimating a wider
        population, and it returns ``0.0`` for constant features without
        crashing.
    """
    rows = list(rows)
    if not rows:
        raise ValueError("compute_user_baseline requires at least one row")

    login_hours = np.array([login_time_to_hours(r["login_time"]) for r in rows], dtype=float)
    access_counts = np.array([int(r["access_count"]) for r in rows], dtype=float)
    resources = [str(r["resource_type"]) for r in rows]
    dates = [str(r["activity_date"]) for r in rows]

    counts = Counter(resources)
    total = sum(counts.values())
    # Sorted keys -> deterministic JSON; proportions support Phase 5 rarity scoring.
    distribution = {category: counts[category] / total for category in sorted(counts)}
    # Most frequent resource; ties broken alphabetically for determinism.
    common_resource_type = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    return {
        "average_login_time": float(np.mean(login_hours)),
        "sd_login_time": float(np.std(login_hours, ddof=0)),
        "average_access_count": float(np.mean(access_counts)),
        "sd_access_count": float(np.std(access_counts, ddof=0)),
        "common_resource_type": common_resource_type,
        "resource_distribution_json": json.dumps(distribution),
        "baseline_period": f"{min(dates)} to {max(dates)}",
    }


def build_baselines(db_path=None, min_records=None, clear_existing=True):
    """Build and persist per-user baselines for all eligible users.

    Args:
        db_path: target database; defaults to ``Config.DB_PATH``.
        min_records: minimum activity rows required; defaults to
            ``Config.MIN_RECORDS`` (20).
        clear_existing: when True (default), remove existing ``Baselines`` rows
            first so repeated runs do not accumulate duplicates.

    Returns:
        A summary dict: ``eligible_users``, ``excluded_users`` (list of
        ``{user_id, record_count, reason}``), ``baselines_created``,
        ``min_records``, and ``baseline_periods`` (``{user_id: period}``).
    """
    if db_path is None:
        db_path = Config.DB_PATH
    if min_records is None:
        min_records = Config.MIN_RECORDS

    init_db(db_path)  # idempotent: ensure schema exists

    eligible_users = 0
    excluded_users = []
    baselines_created = 0
    baseline_periods = {}

    conn = connect(db_path)
    try:
        if clear_existing:
            conn.execute("DELETE FROM Baselines")

        users = conn.execute("SELECT user_id FROM Users ORDER BY user_id").fetchall()
        for user in users:
            user_id = user["user_id"]
            rows = conn.execute(
                "SELECT login_time, access_count, resource_type, activity_date "
                "FROM ActivityLogs WHERE user_id = ? ORDER BY activity_date",
                (user_id,),
            ).fetchall()

            if len(rows) < min_records:
                reason = f"fewer than {min_records} records ({len(rows)})"
                excluded_users.append(
                    {"user_id": user_id, "record_count": len(rows), "reason": reason}
                )
                logger.info("Excluding user %s: %s", user_id, reason)
                continue

            baseline = compute_user_baseline(rows)
            conn.execute(
                "INSERT INTO Baselines "
                "(user_id, average_login_time, sd_login_time, average_access_count, "
                " sd_access_count, common_resource_type, resource_distribution_json, "
                " baseline_period) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    baseline["average_login_time"],
                    baseline["sd_login_time"],
                    baseline["average_access_count"],
                    baseline["sd_access_count"],
                    baseline["common_resource_type"],
                    baseline["resource_distribution_json"],
                    baseline["baseline_period"],
                ),
            )
            eligible_users += 1
            baselines_created += 1
            baseline_periods[user_id] = baseline["baseline_period"]

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "eligible_users": eligible_users,
        "excluded_users": excluded_users,
        "baselines_created": baselines_created,
        "min_records": min_records,
        "baseline_periods": baseline_periods,
    }


def main():
    """Build baselines for the configured database and print a summary."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = build_baselines()
    print("Baseline summary:")
    print(f"  min_records:       {summary['min_records']}")
    print(f"  eligible_users:    {summary['eligible_users']}")
    print(f"  baselines_created: {summary['baselines_created']}")
    print(f"  excluded_users:    {summary['excluded_users']}")


if __name__ == "__main__":
    main()
