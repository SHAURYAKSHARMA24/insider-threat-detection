"""Phase 5 tests: Z-score anomaly scoring (FR4 / NFR1).

All scoring is pure and in-memory; the real-data smoke test builds a small
temporary database only to source a realistic record + baseline pair.
"""
import math
from pathlib import Path

import pytest

from app.baseline import build_baselines
from app.db import connect
from app.ingest import ingest_activity
from app.scoring import (
    build_anomaly_reason,
    resource_rarity,
    responsible_feature,
    score_record,
    z_score,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_CSV = PROJECT_ROOT / "data" / "activity_baseline.csv"

# A controlled baseline used across several tests.
BASE = {
    "average_login_time": 9.0,
    "sd_login_time": 1.0,
    "average_access_count": 20.0,
    "sd_access_count": 5.0,
    "resource_distribution_json": '{"HR": 0.6, "General": 0.4}',
}


# --------------------------------------------------------------------------- #
# 1. Z-score correctness
# --------------------------------------------------------------------------- #
def test_z_score_known_value():
    assert z_score(10.0, 5.0, 2.5) == pytest.approx(2.0)


def test_z_score_below_mean_is_absolute():
    assert z_score(0.0, 5.0, 2.5) == pytest.approx(2.0)


def test_z_score_sd_zero_same_value():
    assert z_score(5.0, 5.0, 0.0) == 0.0


def test_z_score_sd_zero_different_value_is_finite_high():
    result = z_score(7.0, 5.0, 0.0)
    assert result == 999.0
    assert math.isfinite(result)


def test_z_score_never_nan_or_inf():
    for value, mean, sd in [(10, 5, 2.5), (0, 5, 2.5), (5, 5, 0), (7, 5, 0)]:
        assert math.isfinite(z_score(value, mean, sd))


# --------------------------------------------------------------------------- #
# 2. Resource rarity
# --------------------------------------------------------------------------- #
def test_common_resource_scores_lower_than_rare():
    dist = '{"HR": 0.6, "General": 0.3, "Finance": 0.1}'
    assert resource_rarity("HR", dist) < resource_rarity("Finance", dist)


def test_unseen_resource_scores_higher_than_rare():
    dist = '{"HR": 0.6, "General": 0.3, "Finance": 0.1}'
    assert resource_rarity("SourceCode", dist) > resource_rarity("Finance", dist)


def test_resource_rarity_invalid_json_raises():
    with pytest.raises(ValueError):
        resource_rarity("HR", "{not valid json")


@pytest.mark.parametrize("dist", ['{"HR": 1.5}', '{"HR": -0.2}', '{"HR": "x"}'])
def test_resource_rarity_invalid_probability_raises(dist):
    with pytest.raises(ValueError):
        resource_rarity("HR", dist)


def test_resource_rarity_is_finite():
    dist = '{"HR": 0.6, "General": 0.4}'
    for resource in ["HR", "General", "Unseen"]:
        assert math.isfinite(resource_rarity(resource, dist))


# --------------------------------------------------------------------------- #
# 3. score_record
# --------------------------------------------------------------------------- #
def test_score_record_login_time_responsible():
    record = {"login_time": "12:00", "access_count": 20, "resource_type": "HR"}
    scored = score_record(record, BASE)
    assert scored["login_time_z"] == pytest.approx(3.0)       # |12-9|/1
    assert scored["access_count_z"] == pytest.approx(0.0)     # |20-20|/5
    assert scored["resource_type_z"] == pytest.approx(-math.log(0.6))
    assert scored["deviation_score"] == pytest.approx(3.0)    # the max
    assert scored["responsible_feature"] == "login_time"
    assert "login_time" in scored["reason"]
    assert "3.00" in scored["reason"]


def test_score_record_access_count_responsible():
    record = {"login_time": "09:00", "access_count": 40, "resource_type": "HR"}
    scored = score_record(record, BASE)
    assert scored["access_count_z"] == pytest.approx(4.0)     # |40-20|/5
    assert scored["responsible_feature"] == "access_count"
    assert scored["deviation_score"] == pytest.approx(4.0)
    assert "access_count" in scored["reason"] and "4.00" in scored["reason"]


def test_score_record_resource_type_responsible():
    record = {"login_time": "09:00", "access_count": 20, "resource_type": "Confidential"}
    scored = score_record(record, BASE)
    assert scored["responsible_feature"] == "resource_type"
    assert scored["deviation_score"] == pytest.approx(-math.log(0.001))
    assert "Rare resource_type" in scored["reason"]


# --------------------------------------------------------------------------- #
# 4. Deterministic tie-breaking
# --------------------------------------------------------------------------- #
def test_tie_break_login_time_beats_access_count():
    feature, value = responsible_feature(
        {"login_time": 3.0, "access_count": 3.0, "resource_type": 1.0}
    )
    assert feature == "login_time"
    assert value == 3.0


def test_tie_break_access_count_beats_resource_type():
    feature, value = responsible_feature(
        {"login_time": 1.0, "access_count": 3.0, "resource_type": 3.0}
    )
    assert feature == "access_count"
    assert value == 3.0


# --------------------------------------------------------------------------- #
# 5. Real-data smoke test
# --------------------------------------------------------------------------- #
def test_real_data_scoring_returns_finite_keys(tmp_path):
    db_path = str(tmp_path / "itd.sqlite")
    ingest_activity(str(BASELINE_CSV), db_path=db_path)
    build_baselines(db_path=db_path)

    conn = connect(db_path)
    baseline = dict(conn.execute("SELECT * FROM Baselines LIMIT 1").fetchone())
    record = dict(
        conn.execute(
            "SELECT login_time, access_count, resource_type FROM ActivityLogs "
            "WHERE user_id = ? LIMIT 1",
            (baseline["user_id"],),
        ).fetchone()
    )
    conn.close()

    scored = score_record(record, baseline)
    for key in ("login_time_z", "access_count_z", "resource_type_z", "deviation_score"):
        assert key in scored
        assert math.isfinite(scored[key])
    assert scored["responsible_feature"] in ("login_time", "access_count", "resource_type")
    assert isinstance(scored["reason"], str) and scored["reason"]
