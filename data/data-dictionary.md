# Synthetic Dataset Specification (Data Dictionary)

All evaluation data is **synthetic** (AT2 NFR2). No real or personal data is used. Data is
produced by `data/generate_data.py` (Phase 1) using a **fixed random seed** for
reproducibility. This document specifies the design only; generation is implemented later.

## Files produced

| File | Purpose | Target size |
|---|---|---|
| `activity_baseline.csv` | Bulk historical activity used to build per-user baselines | >= 10,000 rows, ~15-25 users |
| `scenario_normal.csv` | Labelled normal-behaviour scenario | >= 50 rows |
| `scenario_after_hours.csv` | Labelled anomalous scenario (unusual login times) | >= 50 rows |
| `scenario_exfiltration.csv` | Labelled anomalous scenario (access spike / rare resource) | >= 50 rows |

## Columns

| Column | Type | Range / allowed values | Notes |
|---|---|---|---|
| `user_id` | string | e.g. `U001`-`U025` | Stable identifier; primary key in `Users` |
| `user_name` | string | e.g. `user001` | Display name |
| `user_role` | string | {analyst, engineer, manager, admin, support} | Categorical role |
| `activity_date` | date | `YYYY-MM-DD`, over a ~60-90 day window | One or more records per user per day |
| `login_time` | time | `HH:MM` (24-hour) | Centred on each user's individual mean login hour |
| `access_count` | integer | typically 5-200 | Per-user mean/spread; mildly right-skewed |
| `resource_type` | string | {email, fileshare, database, codeRepo, hr, finance} | Each user has a typical subset |
| `label` | string | {normal, anomalous} | **Scenario files only** -- ground-truth for evaluation. Absent from the baseline file. |

## Per-user "normal" model

At generation time each user is assigned an individual behavioural profile:

- a **mean login hour** (e.g. 8-10) with a small standard deviation;
- a **mean daily access count** with a moderate standard deviation;
- a small set of **common resource types** with an associated probability distribution.

Normal records are sampled from these per-user distributions, so a statistically meaningful
baseline (mean + standard deviation per feature) can be computed for every user with at
least `MIN_RECORDS` (20) records, satisfying FR3.

## Anomaly injection (scenario files)

- **After-hours:** a subset of records shifts `login_time` into late-night hours well
  outside the user's baseline login-hour distribution (drives a login-time Z-score).
- **Exfiltration:** a subset of records spikes `access_count` and/or uses a `resource_type`
  that is rare for that user (drives an access-count Z-score and/or categorical rarity).
- Both **gradual** and **abrupt** deviations are included so detection is exercised across a
  range of conditions (mitigates AT2 risk R1).

## Reproducibility

- The NumPy RNG is seeded with a fixed constant recorded in `generate_data.py`.
- Regenerating with the same seed reproduces identical files, supporting repeatable
  evaluation (FR9 / Objective 4).
