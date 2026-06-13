"""Phase 7 tests: backend API routes (FR2, FR7, FR8).

A module-scoped fixture builds one populated temporary database (baseline +
after-hours scenario, fully processed) and returns a Flask test client pointed
at it.
"""
from pathlib import Path

import pytest

from app.anomalies import process_unscored_activity
from app.baseline import build_baselines
from app.config import TestingConfig
from app.ingest import ingest_activity
from app import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_CSV = PROJECT_ROOT / "data" / "activity_baseline.csv"
AFTER_HOURS_CSV = PROJECT_ROOT / "data" / "scenario_after_hours.csv"

ANOMALY_KEYS = {
    "anomaly_id", "user_id", "activity_date", "login_time", "resource_type",
    "access_count", "deviation_score", "severity_level", "anomaly_reason",
    "detection_timestamp",
}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("routes") / "itd.sqlite")
    ingest_activity(str(BASELINE_CSV), db_path=db_path)
    build_baselines(db_path=db_path)
    ingest_activity(str(AFTER_HOURS_CSV), db_path=db_path)
    process_unscored_activity(db_path=db_path, clear_existing=True)

    app = create_app(TestingConfig)
    app.config["DB_PATH"] = db_path
    return app.test_client()


# --------------------------------------------------------------------------- #
# Landing + summary
# --------------------------------------------------------------------------- #
def test_index_renders_dashboard_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    assert "Insider Threat Detection" in resp.get_data(as_text=True)


def test_summary_shape_and_values(client):
    resp = client.get("/api/summary")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == {
        "total_activity_logs", "total_anomalies",
        "high_risk_anomalies", "users_monitored",
    }
    assert body["total_activity_logs"] == 12162  # 12092 baseline + 70 scenario
    assert body["users_monitored"] == 20
    assert body["total_anomalies"] > 0
    assert body["high_risk_anomalies"] <= body["total_anomalies"]


# --------------------------------------------------------------------------- #
# /api/anomalies — base + JSON shape
# --------------------------------------------------------------------------- #
def test_anomalies_no_filters_returns_all(client):
    resp = client.get("/api/anomalies")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == len(body["anomalies"])
    assert body["count"] > 0
    # Sorted by deviation_score descending.
    scores = [a["deviation_score"] for a in body["anomalies"]]
    assert scores == sorted(scores, reverse=True)
    # Each row has the expected shape.
    assert ANOMALY_KEYS <= set(body["anomalies"][0])


def test_missing_params_does_not_break(client):
    # No query string at all is equivalent to "no filters".
    assert client.get("/api/anomalies").status_code == 200
    assert client.get("/api/anomalies?").status_code == 200


# --------------------------------------------------------------------------- #
# Individual filters
# --------------------------------------------------------------------------- #
def test_filter_by_user(client):
    all_rows = client.get("/api/anomalies").get_json()["anomalies"]
    target_user = all_rows[0]["user_id"]
    body = client.get(f"/api/anomalies?user={target_user}").get_json()
    assert body["count"] > 0
    assert all(a["user_id"] == target_user for a in body["anomalies"])


def test_filter_by_severity(client):
    body = client.get("/api/anomalies?severity=High").get_json()
    assert body["count"] > 0
    assert all(a["severity_level"] == "High" for a in body["anomalies"])


def test_filter_by_date_range(client):
    # Scenario after-hours rows are dated 2025-05-xx; baseline is Jan-Apr.
    body = client.get("/api/anomalies?start=2025-05-01").get_json()
    assert body["count"] > 0
    assert all(a["activity_date"] >= "2025-05-01" for a in body["anomalies"])

    body_end = client.get("/api/anomalies?end=2025-04-30").get_json()
    assert all(a["activity_date"] <= "2025-04-30" for a in body_end["anomalies"])


# --------------------------------------------------------------------------- #
# Combined + empty
# --------------------------------------------------------------------------- #
def test_combined_filters(client):
    body = client.get("/api/anomalies?severity=High&start=2025-05-01").get_json()
    assert body["count"] > 0
    assert all(
        a["severity_level"] == "High" and a["activity_date"] >= "2025-05-01"
        for a in body["anomalies"]
    )


def test_empty_result_for_unknown_user(client):
    body = client.get("/api/anomalies?user=NO_SUCH_USER").get_json()
    assert body["count"] == 0
    assert body["anomalies"] == []


def test_empty_result_for_unknown_severity(client):
    body = client.get("/api/anomalies?severity=Critical").get_json()
    assert body["count"] == 0


# --------------------------------------------------------------------------- #
# Security: parameterised SQL resists injection
# --------------------------------------------------------------------------- #
def test_sql_injection_in_query_params_is_safe(client):
    # A classic injection string must be treated as a literal value -> no match.
    injection = "U001' OR '1'='1"
    body = client.get("/api/anomalies", query_string={"user": injection}).get_json()
    assert body["count"] == 0

    # A destructive payload must not drop the table.
    drop = "High'); DROP TABLE Anomalies;--"
    resp = client.get("/api/anomalies", query_string={"severity": drop})
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 0

    # Table is intact: summary still reports anomalies.
    assert client.get("/api/summary").get_json()["total_anomalies"] > 0
