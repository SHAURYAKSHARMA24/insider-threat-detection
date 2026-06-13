"""CSV ingestion for the Insider Threat Detection System (Phase 3, FR1).

Loads structured activity CSV data, validates it explicitly, and inserts
distinct users into ``Users`` and valid activity records into ``ActivityLogs``
using parameterised SQL inside a single transaction.

Scope note: the ``label`` column (evaluation ground truth) is *validated* when
present but is **not** inserted into ``ActivityLogs`` -- the schema has no
``label`` column and labels are only consumed later (Phase 9 evaluation).
"""
import re
from pathlib import Path

import pandas as pd

from app.config import Config
from app.db import connect, init_db

REQUIRED_COLUMNS = [
    "user_id",
    "user_name",
    "user_role",
    "activity_date",
    "login_time",
    "access_count",
    "resource_type",
]
NON_EMPTY_TEXT_COLUMNS = ["user_id", "user_name", "user_role", "resource_type"]
VALID_LABELS = {"normal", "anomalous"}

_LOGIN_TIME_RE = r"^([01]\d|2[0-3]):[0-5]\d$"
_INTEGER_RE = r"^\d+$"


def load_csv(path):
    """Read a CSV from disk as strings, leaving validation to ``validate_rows``.

    All cells are read as strings with blanks preserved (``keep_default_na``
    off) so that validation -- not pandas' type inference -- decides what is
    acceptable.

    Args:
        path: path to the CSV file.

    Returns:
        A :class:`pandas.DataFrame`. A completely empty file yields an empty
        (0x0) DataFrame rather than raising.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    try:
        return pd.read_csv(file_path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def validate_rows(df):
    """Partition ``df`` into accepted and rejected rows.

    Args:
        df: a DataFrame of string-typed activity rows.

    Returns:
        ``(clean_df, rejected_df)``. ``rejected_df`` carries an extra
        ``rejection_reason`` column describing the first failed check.

    Raises:
        ValueError: if any required column is absent (a structural error,
            distinct from a bad row value).
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    reason = pd.Series("", index=df.index, dtype=object)

    def fail(mask, text):
        """Record ``text`` for rows in ``mask`` that have no reason yet."""
        target = mask.fillna(True) & (reason == "")
        reason[target] = text

    # Empty mandatory text fields.
    for col in NON_EMPTY_TEXT_COLUMNS:
        fail(df[col].str.strip() == "", f"empty {col}")

    # activity_date must be a real YYYY-MM-DD date.
    parsed_date = pd.to_datetime(df["activity_date"], format="%Y-%m-%d", errors="coerce")
    fail(parsed_date.isna(), "invalid activity_date")

    # login_time must be HH:MM within 00:00-23:59.
    login_ok = df["login_time"].str.match(_LOGIN_TIME_RE)
    fail(~login_ok.fillna(False), "invalid login_time")

    # access_count must be a positive integer.
    access = df["access_count"].str.strip()
    is_integer = access.str.match(_INTEGER_RE)
    fail(~is_integer.fillna(False), "invalid access_count")
    is_positive = pd.to_numeric(access, errors="coerce") > 0
    fail(is_integer.fillna(False) & ~is_positive.fillna(False), "non-positive access_count")

    # label is optional, but must be valid when present.
    if "label" in df.columns:
        label_ok = df["label"].str.strip().isin(VALID_LABELS)
        fail(~label_ok, "invalid label")

    clean = df[reason == ""].copy()
    rejected = df[reason != ""].copy()
    rejected["rejection_reason"] = reason[reason != ""]
    return clean, rejected


def ingest_activity(path, db_path=None):
    """Load, validate, and insert a CSV of activity data.

    Distinct users are inserted (``INSERT OR IGNORE`` -- existing users are
    left untouched) before their activity rows, so foreign-key integrity holds.
    All inserts run inside a single transaction; any failure rolls back.

    Not idempotent: re-running inserts duplicate ``ActivityLogs`` rows, because
    the schema has no natural uniqueness key for an activity event.

    Args:
        path: path to the activity CSV.
        db_path: target database; defaults to ``Config.DB_PATH``. The schema is
            created if it does not already exist.

    Returns:
        A summary dict with ``rows_read``, ``rows_ingested``, ``rows_rejected``,
        ``users_inserted_or_seen``, and ``rejection_reasons``.
    """
    summary = {
        "rows_read": 0,
        "rows_ingested": 0,
        "rows_rejected": 0,
        "users_inserted_or_seen": 0,
        "rejection_reasons": {},
    }

    df = load_csv(path)
    if df.shape[1] == 0:  # completely empty file (no header, no rows)
        return summary

    clean, rejected = validate_rows(df)
    summary["rows_read"] = len(df)
    summary["rows_rejected"] = len(rejected)
    if not rejected.empty:
        summary["rejection_reasons"] = rejected["rejection_reason"].value_counts().to_dict()

    if db_path is None:
        db_path = Config.DB_PATH
    init_db(db_path)  # idempotent: CREATE TABLE IF NOT EXISTS

    users = clean[["user_id", "user_name", "user_role"]].drop_duplicates(subset="user_id")
    user_rows = list(users.itertuples(index=False, name=None))
    log_rows = [
        (row.user_id, row.login_time, int(row.access_count), row.resource_type, row.activity_date)
        for row in clean.itertuples(index=False)
    ]

    conn = connect(db_path)
    try:
        # Users first so ActivityLogs foreign keys always resolve.
        conn.executemany(
            "INSERT OR IGNORE INTO Users (user_id, user_name, user_role) VALUES (?, ?, ?)",
            user_rows,
        )
        conn.executemany(
            "INSERT INTO ActivityLogs "
            "(user_id, login_time, access_count, resource_type, activity_date) "
            "VALUES (?, ?, ?, ?, ?)",
            log_rows,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    summary["rows_ingested"] = len(log_rows)
    summary["users_inserted_or_seen"] = len(user_rows)
    return summary


def main():
    """Ingest the bundled baseline dataset into the configured database."""
    csv_path = Path(__file__).resolve().parent.parent / "data" / "activity_baseline.csv"
    summary = ingest_activity(str(csv_path))
    print("Ingest summary:", summary)


if __name__ == "__main__":
    main()
