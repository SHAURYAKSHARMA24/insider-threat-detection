"""Phase 0 smoke tests: the Flask app factory builds and /health responds.

These tests verify only the scaffold. Detection, ingestion, and dashboard
behaviour are covered by dedicated test modules in later phases.
"""
from app import create_app
from app.config import TestingConfig


def test_app_factory_creates_app():
    """create_app should return a configured Flask app in testing mode."""
    app = create_app(TestingConfig)
    assert app is not None
    assert app.config["TESTING"] is True


def test_config_thresholds_present():
    """Severity thresholds and the baseline gate must be configured (FR5/FR3)."""
    app = create_app(TestingConfig)
    assert app.config["Z_LOW"] == 2.5
    assert app.config["Z_MEDIUM"] == 3.0
    assert app.config["Z_HIGH"] == 4.0
    assert app.config["MIN_RECORDS"] == 20


def test_health_endpoint_returns_200():
    """The /health route should return HTTP 200 with a JSON ok status."""
    app = create_app(TestingConfig)
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
