# Detection Engine

How a single activity record becomes a deviation score, a responsible feature, a
severity band, and an explainable reason. All logic referenced here lives in
`app/scoring.py` (pure scoring) and `app/anomalies.py` (classification + storage).

## Inputs

Each record is scored against the relevant user's **baseline**, built by
`app/baseline.py`:

| Baseline field | Meaning |
|---|---|
| `average_login_time`, `sd_login_time` | Mean and population SD of login hour (decimal hours) |
| `average_access_count`, `sd_access_count` | Mean and population SD of daily access count |
| `resource_distribution_json` | Sorted JSON `{resource_type: proportion}` over the user's history |
| `common_resource_type` | Modal resource type (ties broken alphabetically) |

Login times (`HH:MM`) are converted to decimal hours by `login_time_to_hours`
(`"09:30" -> 9.5`).

## Per-feature scoring

Three features are scored on a deliberately **common scale** so one threshold applies
to all of them. The record's deviation score is the maximum of the three.

### 1. Numeric features -- absolute Z-score

`login_time` and `access_count` use `z_score(value, mean, sd) = |(value - mean) / sd|`.

Edge case: when `sd == 0` the Z-score is undefined. The function returns:

- `0.0` if the value equals the mean (no deviation), or
- `SD_ZERO_DEVIATION = 999.0` otherwise -- a finite sentinel, never `inf`/`NaN`.

The sentinel guarantees that a user whose history was perfectly constant on a feature
still flags (as High) if they break that pattern. It is explainable but crude; a
principled small-sample fallback is listed in the README roadmap.

### 2. Categorical feature -- calibrated rarity

`resource_type` cannot use a Z-score, so it uses **calibrated surprisal**:

```
score = max(0, -log(p) + log(0.05))
```

where `p` is the resource's proportion in the user's baseline distribution.

| Resource frequency `p` | Approx. score | Interpretation |
|---|---|---|
| `p >= 0.05` (>= 5%) | 0.0 | Common/moderately rare for this user -- not anomalous |
| `p = 0.01` (1%) | ~1.6 | Low-frequency but legitimate; below the 2.5 flag threshold |
| unseen (`p <= 0`) | ~3.9 | Floored at `RESOURCE_UNSEEN_PROBABILITY = 0.001`; flags as High |

The `+log(0.05)` offset is the calibration: it shifts the scale so legitimate
low-frequency resources score below the anomaly threshold while genuinely rare or
unseen resources still score on roughly the same magnitude as a strong Z-score. The
function validates the distribution JSON and rejects non-numeric, NaN/inf, or
out-of-`[0,1]` probabilities.

## Responsible feature and reason

`responsible_feature(scores)` returns the feature with the maximum score. Ties are
broken deterministically by `FEATURE_ORDER = ["login_time", "access_count",
"resource_type"]` -- the incumbent is only replaced on a strictly greater score while
iterating in that order.

The reason string is built for the winning feature:

| Responsible feature | Reason format |
|---|---|
| `login_time` | `Abnormal login_time, Z = <score>` |
| `access_count` | `Abnormal access_count, Z = <score>` |
| `resource_type` | `Rare resource_type, score = <score>` |

This reason is stored on the anomaly row and shown in the dashboard detail panel,
satisfying the explainability requirement (NFR1).

## Severity classification

`classify_severity(score)` maps the deviation score to exactly one band, using the
configurable thresholds from `app/config.py`:

| Band | Condition (default) |
|---|---|
| `None` (not stored) | score < `Z_LOW` (2.5), or non-finite / wrong type |
| `Low` | `Z_LOW` <= score < `Z_MEDIUM` (2.5 .. <3.0) |
| `Medium` | `Z_MEDIUM` <= score < `Z_HIGH` (3.0 .. <4.0) |
| `High` | score >= `Z_HIGH` (>= 4.0) |

Non-finite or wrongly typed scores return `None` and are never stored -- a defensive
guard so a malformed value can never become an anomaly.

## Storage

`anomalies.py` persists flagged records:

- `flag_and_store` scores one record and inserts it only if classified, inside a
  transaction with rollback.
- `process_unscored_activity` batch-scores every `ActivityLogs` row against its user's
  **latest** baseline and bulk-inserts the flagged rows via `executemany`. It can clear
  existing anomalies first (`clear_existing=True`) so repeated demo rebuilds do not
  accumulate duplicates.

Records whose user has no baseline are skipped and counted in `skipped_no_baseline`.

## Worked example

A Finance user whose baseline login hour is mean 8.5, SD 0.9, logs in at 02:00 (2.0
decimal hours):

```
login_time Z = |(2.0 - 8.5) / 0.9| = 7.22
access_count Z = (typical)         = 0.4
resource_type score = (General, common) = 0.0
deviation_score = max(7.22, 0.4, 0.0) = 7.22  -> responsible feature: login_time
severity = High (7.22 >= 4.0)
reason = "Abnormal login_time, Z = 7.22"
```

## Determinism

Given the same database, scoring is fully deterministic: the same inputs yield the
same scores, features, reasons, and severities. The only non-deterministic field is
`detection_timestamp` (wall-clock time at storage), which does not affect any metric.

## Related documents

- [ARCHITECTURE.md](ARCHITECTURE.md) -- where scoring sits in the data flow.
- [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md) -- what a flag does and does not mean.
- [CONFIGURATION.md](CONFIGURATION.md) -- tuning the thresholds.
