"""Phase 1 tests: the synthetic data generator is correct and deterministic.

These tests operate on in-memory DataFrames produced by ``generate_datasets``
so they never depend on previously written CSV files.
"""
import re

import pandas as pd
import pytest

from data.generate_data import (
    COLUMNS,
    RESOURCE_TYPES,
    SEED,
    generate_datasets,
)

LOGIN_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SCENARIO_FILES = ["scenario_normal", "scenario_after_hours", "scenario_exfiltration"]


@pytest.fixture(scope="module")
def datasets():
    """Generate all datasets once for the module."""
    return generate_datasets(SEED)


def test_baseline_has_at_least_10000_rows(datasets):
    assert len(datasets["activity_baseline"]) >= 10_000


def test_baseline_user_count_in_expected_range(datasets):
    user_count = datasets["activity_baseline"]["user_id"].nunique()
    assert 15 <= user_count <= 25


def test_every_baseline_user_has_at_least_20_records(datasets):
    counts = datasets["activity_baseline"].groupby("user_id").size()
    assert counts.min() >= 20


def test_each_scenario_has_at_least_50_records(datasets):
    for name in SCENARIO_FILES:
        assert len(datasets[name]) >= 50, f"{name} has fewer than 50 rows"


def test_scenario_files_contain_expected_labels(datasets):
    # Normal-behaviour scenario: only normal records.
    assert set(datasets["scenario_normal"]["label"]) == {"normal"}
    # Anomalous scenarios: a genuine mix of normal and anomalous.
    for name in ["scenario_after_hours", "scenario_exfiltration"]:
        labels = set(datasets[name]["label"])
        assert "anomalous" in labels, f"{name} has no anomalous records"
        assert "normal" in labels, f"{name} has no normal records"


def test_generation_is_deterministic_with_same_seed():
    first = generate_datasets(SEED)
    second = generate_datasets(SEED)
    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])


def test_required_columns_present_in_every_dataset(datasets):
    for name, df in datasets.items():
        assert list(df.columns) == COLUMNS, f"{name} columns mismatch: {list(df.columns)}"


def test_login_time_matches_hh_mm_format(datasets):
    for name, df in datasets.items():
        bad = [t for t in df["login_time"].unique() if not LOGIN_TIME_RE.match(str(t))]
        assert not bad, f"{name} has malformed login_time values: {bad[:5]}"


def test_access_count_is_positive_integer(datasets):
    for name, df in datasets.items():
        assert pd.api.types.is_integer_dtype(df["access_count"]), f"{name} access_count not int"
        assert (df["access_count"] > 0).all(), f"{name} has non-positive access_count"


def test_resource_type_within_controlled_set(datasets):
    allowed = set(RESOURCE_TYPES)
    for name, df in datasets.items():
        used = set(df["resource_type"].unique())
        assert used <= allowed, f"{name} uses out-of-set resource types: {used - allowed}"
