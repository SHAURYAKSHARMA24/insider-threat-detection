"""Deterministic synthetic activity-data generator for the Insider Threat
Detection System (COM668 AT3, Phase 1).

Produces believable, reproducible synthetic data only -- no real or personal
data, no external downloads (AT2 NFR2). A single seeded NumPy generator
(``SEED = 42``) is threaded through every step, so regenerating reproduces
byte-identical output.

Run:
    python data/generate_data.py

Outputs (written next to this file, in ``data/``):
    activity_baseline.csv       bulk history, all ``normal``  (>= 10,000 rows)
    scenario_normal.csv         labelled normal scenario      (>= 50 rows)
    scenario_after_hours.csv    login-time anomalies          (>= 50 rows)
    scenario_exfiltration.csv   access/resource anomalies     (>= 50 rows)
"""
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
SEED = 42

N_USERS = 20
BASELINE_DAYS = 100
PER_DAY_MIN = 4
PER_DAY_MAX = 8
BASELINE_START = date(2025, 1, 1)
SCENARIO_START = date(2025, 5, 1)
SCENARIO_RECORDS = 70
ANOMALY_FRACTION = 0.4

COLUMNS = [
    "user_id",
    "user_name",
    "user_role",
    "activity_date",
    "login_time",
    "access_count",
    "resource_type",
    "label",
]

# Controlled resource category set (AT3 Phase 1 specification).
RESOURCE_TYPES = [
    "HR",
    "Finance",
    "Engineering",
    "Customer",
    "Admin",
    "SourceCode",
    "Confidential",
    "General",
]

# Resource types that are "sensitive" / unusual for most users -- used by the
# exfiltration scenario.
SENSITIVE_RESOURCES = ["Confidential", "Finance", "SourceCode"]

# Base behavioural profile per role. ``resources`` need not cover every category;
# unlisted categories get a small floor (mild noise) at perturbation time.
#   access: (mean, sd)   login: (mean_hour, sd_hour)
ROLE_PROFILES = {
    "HR": {
        "resources": {"HR": 0.40, "Confidential": 0.20, "General": 0.30, "Admin": 0.10},
        "access": (20, 7),
        "login": (9.0, 0.9),
    },
    "Finance": {
        "resources": {"Finance": 0.45, "Confidential": 0.20, "General": 0.25, "Customer": 0.10},
        "access": (30, 10),
        "login": (8.5, 0.9),
    },
    "Engineering": {
        "resources": {"Engineering": 0.40, "SourceCode": 0.35, "General": 0.20, "Confidential": 0.05},
        "access": (60, 20),
        "login": (10.0, 1.4),
    },
    "Sales": {
        "resources": {"Customer": 0.50, "General": 0.30, "Finance": 0.10, "Admin": 0.10},
        "access": (25, 9),
        "login": (8.0, 1.0),
    },
    "Admin": {
        "resources": {"Admin": 0.40, "General": 0.30, "Confidential": 0.20, "HR": 0.10},
        "access": (35, 12),
        "login": (7.5, 1.1),
    },
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _perturb_weights(base, rng):
    """Build a personalised, normalised resource distribution over all categories.

    Starts from the role's preferences, adds a small floor so any resource is
    occasionally possible (noise), perturbs each weight by +/-15%, and normalises.
    """
    weights = {r: 0.01 for r in RESOURCE_TYPES}
    for resource, prob in base.items():
        weights[resource] = prob
    arr = np.array(
        [max(0.001, weights[r] * (1.0 + rng.normal(0, 0.15))) for r in RESOURCE_TYPES],
        dtype=float,
    )
    arr = arr / arr.sum()
    return {r: float(a) for r, a in zip(RESOURCE_TYPES, arr)}


def _make_normal_record(user, day, rng):
    """Create a single believable ``normal`` activity record for ``user`` on ``day``."""
    hour = int(np.clip(round(rng.normal(user["login_mean"], user["login_sd"])), 5, 21))
    minute = int(rng.integers(0, 60))
    login_time = f"{hour:02d}:{minute:02d}"

    access = int(max(1, round(rng.normal(user["access_mean"], user["access_sd"]))))

    probs = np.array([user["resource_weights"][r] for r in RESOURCE_TYPES], dtype=float)
    probs = probs / probs.sum()
    resource = str(rng.choice(RESOURCE_TYPES, p=probs))

    return {
        "user_id": user["user_id"],
        "user_name": user["user_name"],
        "user_role": user["user_role"],
        "activity_date": day.isoformat(),
        "login_time": login_time,
        "access_count": access,
        "resource_type": resource,
        "label": "normal",
    }


def _sample_normal_records(users, n, rng, start_date=SCENARIO_START, window_days=30):
    """Sample ``n`` normal records across random users and dates in a window."""
    rows = []
    for _ in range(n):
        user = users[int(rng.integers(0, len(users)))]
        day = start_date + timedelta(days=int(rng.integers(0, window_days)))
        rows.append(_make_normal_record(user, day, rng))
    return pd.DataFrame(rows, columns=COLUMNS)


def _default_rng(rng):
    """Return ``rng`` or a fresh seeded generator if none was supplied."""
    return rng if rng is not None else np.random.default_rng(SEED)


# --------------------------------------------------------------------------- #
# Public generation functions
# --------------------------------------------------------------------------- #
def generate_users(n, rng=None):
    """Generate ``n`` users with individual (non-identical) behavioural profiles."""
    rng = _default_rng(rng)
    roles = list(ROLE_PROFILES.keys())
    users = []
    for i in range(n):
        role = roles[i % len(roles)]
        profile = ROLE_PROFILES[role]

        login_mean = profile["login"][0] + rng.normal(0, 0.6)
        login_sd = max(0.4, profile["login"][1] + rng.normal(0, 0.2))
        access_mean = max(5.0, profile["access"][0] + rng.normal(0, profile["access"][1] * 0.3))
        access_sd = max(2.0, profile["access"][1] + rng.normal(0, profile["access"][1] * 0.2))

        users.append(
            {
                "user_id": f"U{i + 1:03d}",
                "user_name": f"user{i + 1:03d}",
                "user_role": role,
                "login_mean": login_mean,
                "login_sd": login_sd,
                "access_mean": access_mean,
                "access_sd": access_sd,
                "resource_weights": _perturb_weights(profile["resources"], rng),
            }
        )
    return users


def generate_normal_activity(users, days, rng=None, start_date=BASELINE_START):
    """Generate normal activity for every user across ``days`` days.

    Each user produces a random number of records per day (PER_DAY_MIN..PER_DAY_MAX),
    guaranteeing every user has well over MIN_RECORDS records (FR3).
    """
    rng = _default_rng(rng)
    rows = []
    for day_offset in range(days):
        day = start_date + timedelta(days=day_offset)
        for user in users:
            count = int(rng.integers(PER_DAY_MIN, PER_DAY_MAX + 1))
            for _ in range(count):
                rows.append(_make_normal_record(user, day, rng))
    return pd.DataFrame(rows, columns=COLUMNS)


def inject_after_hours_scenario(users, rng=None, n_records=SCENARIO_RECORDS,
                                anomaly_fraction=ANOMALY_FRACTION):
    """Build a scenario whose anomalies are unusual (late-night/early) login times."""
    rng = _default_rng(rng)
    df = _sample_normal_records(users, n_records, rng)

    n_anomalies = int(n_records * anomaly_fraction)
    anomaly_idx = rng.choice(df.index.to_numpy(), size=n_anomalies, replace=False)

    for i in anomaly_idx:
        if rng.random() < 0.5:
            hour = int(rng.integers(22, 24))   # 22-23: milder
        else:
            hour = int(rng.integers(0, 5))     # 00-04: stronger
        minute = int(rng.integers(0, 60))
        df.at[i, "login_time"] = f"{hour:02d}:{minute:02d}"
        df.at[i, "label"] = "anomalous"

    return df


def inject_exfiltration_scenario(users, rng=None, n_records=SCENARIO_RECORDS,
                                 anomaly_fraction=ANOMALY_FRACTION):
    """Build a scenario whose anomalies are access-count spikes / rare resources.

    Anomalies mix gradual-looking (~1.8x-3.3x) and abrupt (~5x-8x) access spikes,
    and many switch to a sensitive resource type rare for the user.
    """
    rng = _default_rng(rng)
    df = _sample_normal_records(users, n_records, rng)

    n_anomalies = int(n_records * anomaly_fraction)
    anomaly_idx = rng.choice(df.index.to_numpy(), size=n_anomalies, replace=False)

    for position, i in enumerate(anomaly_idx):
        base = int(df.at[i, "access_count"])
        if position % 2 == 0:
            # gradual-looking: moderate multiplier that ramps across the anomalies
            multiplier = 1.8 + (position / max(1, len(anomaly_idx))) * 1.5
        else:
            # abrupt: large jump
            multiplier = float(rng.uniform(5.0, 8.0))
        df.at[i, "access_count"] = int(max(1, round(base * multiplier)))

        if rng.random() < 0.7:
            df.at[i, "resource_type"] = str(rng.choice(SENSITIVE_RESOURCES))

        df.at[i, "label"] = "anomalous"

    return df


def write_csv(df, path):
    """Write ``df`` to ``path`` deterministically; returns the row count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return len(df)


def generate_datasets(seed=SEED):
    """Generate all four datasets deterministically and return them as a dict.

    A single seeded generator is threaded through every step so two calls with
    the same seed return identical DataFrames.
    """
    rng = np.random.default_rng(seed)
    users = generate_users(N_USERS, rng)
    return {
        "activity_baseline": generate_normal_activity(users, BASELINE_DAYS, rng),
        "scenario_normal": _sample_normal_records(users, SCENARIO_RECORDS, rng),
        "scenario_after_hours": inject_after_hours_scenario(users, rng),
        "scenario_exfiltration": inject_exfiltration_scenario(users, rng),
    }


def main():
    """Generate every dataset and write it to the ``data/`` directory."""
    data_dir = Path(__file__).resolve().parent
    datasets = generate_datasets(SEED)
    for name, df in datasets.items():
        path = data_dir / f"{name}.csv"
        rows = write_csv(df, path)
        labels = df["label"].value_counts().to_dict()
        print(f"{name}.csv: {rows} rows | users={df['user_id'].nunique()} | labels={labels}")


if __name__ == "__main__":
    main()
