"""One-command demo rebuild for the Insider Threat Detection System.

Runs the full deterministic pipeline end to end -- regenerate synthetic data,
ingest the baseline CSV, build per-user baselines, and score/store anomalies --
so a marker (or the AT3 demo) can reproduce the exact database state with a
single command instead of four ordered steps.

Why this exists: ``app.ingest`` is intentionally **not** idempotent (it has no
natural uniqueness key for an activity event), so re-running the manual steps
without first deleting the database silently duplicates ``ActivityLogs`` rows.
This script resets the database by default to guarantee a correct rebuild.

Usage (PowerShell):
    python scripts/rebuild.py            # fresh rebuild (deletes the DB first)
    python scripts/rebuild.py --no-reset # append to the existing DB (advanced)

Expected output on a clean run (deterministic, SEED = 42):
    ingested 12092 rows, 20 users, 0 rejected
    20 baselines built, 0 users excluded
    299 anomalies stored (Low 256 / Medium 41 / High 2)
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.baseline import build_baselines
from app.anomalies import process_unscored_activity
from app.config import Config
from app.ingest import ingest_activity
from data.generate_data import generate_datasets, write_csv

DATA_DIR = PROJECT_ROOT / "data"
BASELINE_CSV = DATA_DIR / "activity_baseline.csv"


def reset_database(db_path):
    """Delete the SQLite database file if it exists (fresh-rebuild guarantee)."""
    path = Path(db_path)
    if path.exists():
        path.unlink()
        print(f"[reset] removed existing database: {path}")
    else:
        print(f"[reset] no existing database to remove: {path}")


def regenerate_data():
    """Regenerate every synthetic CSV deterministically and report row counts."""
    datasets = generate_datasets()
    for name, df in datasets.items():
        rows = write_csv(df, DATA_DIR / f"{name}.csv")
        print(f"[generate] {name}.csv: {rows} rows")


def rebuild(db_path=None, reset=True):
    """Run the full pipeline and return a summary dict of every stage.

    Args:
        db_path: target database; defaults to ``Config.DB_PATH``.
        reset: when True (default), delete the database first so the rebuild is
            from a clean state and ingestion cannot duplicate rows.

    Returns:
        A dict with ``ingest``, ``baseline``, and ``anomaly`` stage summaries.
    """
    if db_path is None:
        db_path = Config.DB_PATH

    if reset:
        reset_database(db_path)

    print("[1/4] generating synthetic data ...")
    regenerate_data()

    print("[2/4] ingesting baseline activity ...")
    ingest_summary = ingest_activity(str(BASELINE_CSV), db_path=db_path)
    print(
        f"        ingested {ingest_summary['rows_ingested']} rows, "
        f"{ingest_summary['users_inserted_or_seen']} users, "
        f"{ingest_summary['rows_rejected']} rejected"
    )

    print("[3/4] building per-user baselines ...")
    baseline_summary = build_baselines(db_path=db_path)
    print(
        f"        {baseline_summary['baselines_created']} baselines built, "
        f"{len(baseline_summary['excluded_users'])} users excluded"
    )

    print("[4/4] scoring and storing anomalies ...")
    anomaly_summary = process_unscored_activity(db_path=db_path, clear_existing=True)
    counts = anomaly_summary["severity_counts"]
    print(
        f"        {anomaly_summary['anomalies_created']} anomalies stored "
        f"(Low {counts['Low']} / Medium {counts['Medium']} / High {counts['High']})"
    )

    print("\nRebuild complete. Start the dashboard with:  python run.py")
    return {
        "ingest": ingest_summary,
        "baseline": baseline_summary,
        "anomaly": anomaly_summary,
    }


def main(argv=None):
    """CLI entry point for the demo rebuild."""
    parser = argparse.ArgumentParser(description="Rebuild the demo database end to end.")
    parser.add_argument(
        "--reset",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delete the database before rebuilding (default: on). Use --no-reset to append.",
    )
    args = parser.parse_args(argv)
    rebuild(reset=args.reset)


if __name__ == "__main__":
    main()
