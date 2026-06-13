# Synthetic Dataset Specification (Data Dictionary)

All evaluation data is **synthetic** (AT2 NFR2). No real or personal data is used. Data is
produced by `data/generate_data.py` using a **fixed random seed (`SEED = 42`)** so generation
is fully deterministic and reproducible.

## Files produced

| File | Purpose | Target size |
|---|---|---|
| `activity_baseline.csv` | Bulk historical activity used to build per-user baselines | >= 10,000 rows, ~20 users (all `normal`) |
| `scenario_normal.csv` | Labelled normal-behaviour scenario | >= 50 rows (all `normal`) |
| `scenario_after_hours.csv` | Labelled anomalous scenario (unusual login times) | >= 50 rows (mix) |
| `scenario_exfiltration.csv` | Labelled anomalous scenario (access spike / rare resource) | >= 50 rows (mix) |

## Columns (present in **every** file)

| Column | Type | Range / allowed values | Notes |
|---|---|---|---|
| `user_id` | string | `U001`-`U020` | Stable identifier; primary key in `Users` |
| `user_name` | string | `user001`-`user020` | Display name |
| `user_role` | string | {HR, Finance, Engineering, Sales, Admin} | Role drives resource preference and access-count range |
| `activity_date` | date | `YYYY-MM-DD` | Baseline over a ~100-day window; scenarios in a later window |
| `login_time` | time | `HH:MM` (24-hour) | Normal logins clipped to working hours (~05:00-21:00) |
| `access_count` | integer | positive int, typically ~5-200 | Per-user mean/spread; role-influenced |
| `resource_type` | string | {HR, Finance, Engineering, Customer, Admin, SourceCode, Confidential, General} | Each user has a typical weighted subset |
| `label` | string | {normal, anomalous} | `normal` for baseline + normal activity; `anomalous` for injected scenario anomalies |

## Per-user "normal" model

Each of the ~20 users is assigned an individual behavioural profile derived from their role
but **perturbed per user** so no two users are identical:

- a **mean login hour** (role base + per-user offset) with a small standard deviation;
- a **mean daily access count** (role base + per-user offset) with a moderate standard
  deviation;
- a **personalised weighted distribution** over the resource categories (role preferences,
  perturbed, with a small floor so any resource is occasionally possible — mild noise).

Each user generates several records per day across the baseline window, so every user has far
more than the `MIN_RECORDS` (20) needed for a statistically meaningful baseline (FR3).

### Role influence (base profiles, before per-user perturbation)

| Role | Preferred resources | Access-count range | Typical login |
|---|---|---|---|
| HR | HR, Confidential, General | lower | ~09:00 |
| Finance | Finance, Confidential, General | moderate | ~08:30 |
| Engineering | Engineering, SourceCode, General | higher | ~10:00 |
| Sales | Customer, General, Finance | moderate | ~08:00 |
| Admin | Admin, General, Confidential | moderate-high | ~07:30 |

## Anomaly injection (scenario files)

- **After-hours:** a subset (~40%) of records shift `login_time` into late-night/early-morning
  hours (22:00-04:00) while access count and resource stay normal — so the anomaly is
  specifically the login time. Severity is varied (mild 22:xx-23:xx vs stronger 00:xx-04:xx),
  not uniformly extreme.
- **Exfiltration:** a subset (~40%) of records spike `access_count` (a mix of **gradual**
  ~1.8x-3.3x and **abrupt** ~5x-8x multipliers) and/or switch `resource_type` to a sensitive
  type rare for that user (`Confidential`, `Finance`, `SourceCode`).

## Reproducibility

- The NumPy RNG is seeded with `SEED = 42`; a single generator instance is threaded through
  all generation steps.
- Regenerating reproduces byte-identical files, supporting repeatable evaluation
  (FR9 / Objective 4).
