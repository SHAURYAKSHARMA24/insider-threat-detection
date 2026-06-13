"""SQLite data-access layer for the Insider Threat Detection System (Phase 2).

Responsibilities are deliberately narrow: open correctly-configured SQLite
connections, create the schema from ``data/schema.sql``, and manage the
request-scoped connection within Flask. Ingestion, baseline, and scoring logic
live in later phases and build on top of this layer.

Two usage modes are supported:

* **Standalone** (scripts / tests): call :func:`connect` or :func:`init_db`
  with an explicit ``db_path`` -- no Flask app context required.
* **Within Flask**: :func:`get_db` returns a connection cached on ``flask.g``
  for the current request, and :func:`init_app` registers its teardown.
"""
import sqlite3
from pathlib import Path

from flask import current_app, g

# Path to the canonical schema authored in Phase 0.
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data" / "schema.sql"


def connect(db_path):
    """Open a SQLite connection configured for this application.

    Foreign-key enforcement is OFF by default in SQLite and is per-connection,
    so it is enabled explicitly here for every connection. Rows are returned as
    :class:`sqlite3.Row` so callers can access columns by name.

    Args:
        db_path: filesystem path to the SQLite database file.

    Returns:
        A configured :class:`sqlite3.Connection`.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path=None):
    """Create all tables by executing ``data/schema.sql``.

    The schema uses ``CREATE TABLE IF NOT EXISTS``, so this is safe to run
    repeatedly. The parent directory is created if it does not yet exist.

    Args:
        db_path: target database path. When omitted, the active Flask app's
            ``DB_PATH`` configuration value is used.
    """
    if db_path is None:
        db_path = current_app.config["DB_PATH"]

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    try:
        with open(SCHEMA_PATH, encoding="utf-8") as schema_file:
            conn.executescript(schema_file.read())
        conn.commit()
    finally:
        conn.close()


def get_db():
    """Return the request-scoped connection, opening one on first use.

    Must be called within a Flask application context. The connection is cached
    on ``flask.g`` and closed automatically at the end of the request by
    :func:`close_db` (registered via :func:`init_app`).
    """
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(exception=None):  # noqa: ARG001 - signature required by Flask teardown
    """Close and discard the request-scoped connection if one was opened."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    """Wire the data layer into a Flask app (registers connection teardown)."""
    app.teardown_appcontext(close_db)
