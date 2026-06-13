"""Dashboard and API routes for the Insider Threat Detection System.

Read-only JSON endpoints that surface stored anomalies and summary counts for
the dashboard (FR2, FR7, FR8). All filtering uses parameterised SQL; no values
are ever string-interpolated into a query.

The root route renders the dashboard shell; the dashboard then consumes the
JSON API endpoints client-side.
"""
import csv
import io

from flask import Blueprint, Response, jsonify, render_template, request

from app.db import get_db

bp = Blueprint("api", __name__)

# Columns returned by the anomaly query, in display/export order.
ANOMALY_COLUMNS = [
    "anomaly_id", "user_id", "activity_date", "login_time", "resource_type",
    "access_count", "deviation_score", "severity_level", "anomaly_reason",
    "detection_timestamp",
]


def _anomaly_query(args):
    """Build the parameterised anomaly SQL and params from request filters.

    Shared by the JSON (:func:`api_anomalies`) and CSV (:func:`export_anomalies`)
    endpoints so both apply identical, injection-safe filtering. Returns
    ``(sql, params, filters)`` where ``filters`` echoes the applied values.
    """
    user = args.get("user")
    start = args.get("start")
    end = args.get("end")
    severity = args.get("severity")

    clauses = []
    params = []
    if user:
        clauses.append("a.user_id = ?")
        params.append(user)
    if start:
        clauses.append("l.activity_date >= ?")
        params.append(start)
    if end:
        clauses.append("l.activity_date <= ?")
        params.append(end)
    if severity:
        clauses.append("a.severity_level = ?")
        params.append(severity)

    sql = (
        "SELECT a.anomaly_id, a.user_id, l.activity_date, l.login_time, "
        "l.resource_type, l.access_count, "
        "a.deviation_score, a.severity_level, a.anomaly_reason, a.detection_timestamp "
        "FROM Anomalies a JOIN ActivityLogs l ON a.log_id = l.log_id"
    )
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY a.deviation_score DESC"

    filters = {"user": user, "start": start, "end": end, "severity": severity}
    return sql, params, filters


@bp.route("/")
def index():
    """Render the dashboard shell (it loads data from the JSON API client-side)."""
    return render_template("dashboard.html")


@bp.route("/api/summary")
def api_summary():
    """Return aggregate dashboard counts (FR7 summary row)."""
    db = get_db()
    total_logs = db.execute("SELECT COUNT(*) FROM ActivityLogs").fetchone()[0]
    total_anomalies = db.execute("SELECT COUNT(*) FROM Anomalies").fetchone()[0]
    high_risk = db.execute(
        "SELECT COUNT(*) FROM Anomalies WHERE severity_level = ?", ("High",)
    ).fetchone()[0]
    users_monitored = db.execute("SELECT COUNT(*) FROM Users").fetchone()[0]
    return jsonify(
        total_activity_logs=total_logs,
        total_anomalies=total_anomalies,
        high_risk_anomalies=high_risk,
        users_monitored=users_monitored,
    )


@bp.route("/api/anomalies")
def api_anomalies():
    """Return flagged anomalies as JSON, optionally filtered (FR8).

    Query parameters (all optional, combinable):
        user:     exact ``user_id`` match.
        start:    inclusive lower bound on the activity date (YYYY-MM-DD).
        end:      inclusive upper bound on the activity date (YYYY-MM-DD).
        severity: exact severity band (Low/Medium/High).

    Missing parameters are simply not applied. Unknown/garbage values match no
    rows (an empty result), never an error, because every value is bound as a
    SQL parameter rather than concatenated into the query.
    """
    sql, params, filters = _anomaly_query(request.args)
    rows = get_db().execute(sql, params).fetchall()
    anomalies = [dict(row) for row in rows]
    return jsonify(count=len(anomalies), filters=filters, anomalies=anomalies)


@bp.route("/api/anomalies.csv")
def export_anomalies():
    """Export the filtered anomalies as a downloadable CSV file (FR10).

    Accepts the same optional ``user``/``start``/``end``/``severity`` filters as
    :func:`api_anomalies` so the dashboard can export exactly what the analyst is
    currently viewing. Returns ``text/csv`` with an attachment disposition.
    """
    sql, params, _ = _anomaly_query(request.args)
    rows = get_db().execute(sql, params).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ANOMALY_COLUMNS)
    for row in rows:
        writer.writerow([row[column] for column in ANOMALY_COLUMNS])

    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=anomalies.csv"},
    )
