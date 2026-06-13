"""Phase 8 tests: dashboard render/smoke tests (FR7, FR8, NFR5).

These assert the shell renders and references its assets. Browser/JS behaviour
is exercised manually (no headless browser in the test tooling).
"""
from app import create_app
from app.config import TestingConfig


def _client():
    return create_app(TestingConfig).test_client()


def test_dashboard_renders_200():
    resp = _client().get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type


def test_dashboard_contains_root_elements():
    html = _client().get("/").get_data(as_text=True)
    for marker in [
        'id="summary-tiles"',
        'id="anomaly-rows"',
        'id="detail-panel"',
        'id="f-user"',
        'id="f-severity"',
        'id="btn-apply"',
        'id="btn-clear"',
        'id="empty-state"',
    ]:
        assert marker in html, f"missing dashboard element: {marker}"


def test_dashboard_references_static_assets():
    html = _client().get("/").get_data(as_text=True)
    assert "css/styles.css" in html
    assert "js/dashboard.js" in html


def test_static_assets_are_served():
    client = _client()
    css = client.get("/static/css/styles.css")
    js = client.get("/static/js/dashboard.js")
    assert css.status_code == 200
    assert js.status_code == 200
    assert "anomaly-table" in css.get_data(as_text=True)
    assert "loadAnomalies" in js.get_data(as_text=True)
