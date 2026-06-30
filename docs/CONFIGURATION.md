# Configuration

All tunable behaviour is centralised in `app/config.py` so detection thresholds remain
configurable (AT2 FR5) rather than scattered across modules. This document lists every
parameter, its default, and its effect.

## Configuration classes

| Class | Used by | Database |
|---|---|---|
| `Config` | The application and all CLI tools | `instance/itd.sqlite` |
| `TestingConfig` | The pytest suite (`TESTING = True`) | `instance/itd_test.sqlite` |

`TestingConfig` points at a separate database file so tests never touch demo data.

## Detection thresholds

| Parameter | Default | Effect |
|---|---|---|
| `Z_LOW` | `2.5` | Minimum deviation score to be flagged at all; lower bound of the Low band |
| `Z_MEDIUM` | `3.0` | Lower bound of the Medium band |
| `Z_HIGH` | `4.0` | Lower bound of the High band |

The bands are mutually exclusive:

```
not flagged: score < Z_LOW
Low:         Z_LOW    <= score < Z_MEDIUM
Medium:      Z_MEDIUM <= score < Z_HIGH
High:        score >= Z_HIGH
```

Raising `Z_LOW` reduces both false positives and recall; lowering it does the reverse.
The evaluation CLI prints a threshold-sensitivity sweep (2.0 / 2.5 / 3.0 / 3.5 / 4.0)
so the trade-off is visible. **Changing these defaults changes the published metrics
and the stored anomaly counts** -- keep them at their committed values unless you intend
to re-evaluate.

## Baseline gating

| Parameter | Default | Effect |
|---|---|---|
| `MIN_RECORDS` | `20` | Minimum activity rows before a user gets a baseline (AT2 FR3). Users below this are excluded and logged. |

## Paths

| Parameter | Default | Notes |
|---|---|---|
| `BASE_DIR` | parent of `app/` | Project root, derived at import time |
| `INSTANCE_DIR` | `<root>/instance` | Holds the runtime SQLite file (git-ignored) |
| `DB_PATH` | `<instance>/itd.sqlite` | Active database; `TestingConfig` overrides to `itd_test.sqlite` |

## Scoring calibration constants

These live in `app/scoring.py` (not `config.py`) because they define the scoring scale
itself rather than an operational threshold. Documented here for completeness:

| Constant | Default | Meaning |
|---|---|---|
| `SD_ZERO_DEVIATION` | `999.0` | Finite sentinel score when a zero-SD baseline is violated |
| `RESOURCE_RARITY_REFERENCE_PROBABILITY` | `0.05` | Resources at/above this frequency score 0 |
| `RESOURCE_UNSEEN_PROBABILITY` | `0.001` | Floor probability for an unseen resource type |
| `FEATURE_ORDER` | `[login_time, access_count, resource_type]` | Deterministic tie-break order |

## Data generation

The synthetic generator (`data/generate_data.py`) is parameterised at the top of the
file. Changing any of these alters the dataset and therefore the metrics:

| Parameter | Default |
|---|---|
| `SEED` | `42` |
| `N_USERS` | `20` |
| `BASELINE_DAYS` | `100` |
| `SCENARIO_RECORDS` | `70` |
| `ANOMALY_FRACTION` | `0.4` |

## Environment notes

- **Python:** 3.11+ (CI runs 3.11). Developed and verified on 3.13.
- **No environment variables are required.** All configuration is in-code; there are no
  secrets, API keys, or external services.
- **Port:** `run.py` serves on `127.0.0.1:5000`. If that port is in use, start via the
  Flask CLI with an explicit port, e.g.
  `python -m flask --app run:app run --host 127.0.0.1 --port 5050`.

## Related documents

- [DETECTION_ENGINE.md](DETECTION_ENGINE.md) -- how the thresholds and constants are used.
- [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md) -- the assumptions the defaults encode.
