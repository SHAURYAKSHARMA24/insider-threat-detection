# Phase 9 Evaluation Report

## Scenario Files

All three labelled Objective 4 scenario files are present in `data/`:

| Scenario file | Purpose | Records | Ground-truth labels |
|---|---:|---:|---:|
| `data/scenario_normal.csv` | Normal-only activity used to estimate false positives | 70 | 70 normal, 0 anomalous |
| `data/scenario_after_hours.csv` | Late-night / early-login anomaly scenario | 70 | 42 normal, 28 anomalous |
| `data/scenario_exfiltration.csv` | Access-count spike and unusual-resource scenario | 70 | 42 normal, 28 anomalous |

No additional scenario file was required for Phase 9 because the normal,
after-hours, and exfiltration/resource/access-spike labelled scenarios already
exist.

## Evaluation Method

The evaluator in `app/evaluation.py` loads each labelled scenario CSV, validates
the same activity fields used by ingestion, and scores each row in memory
against the latest persisted per-user baseline. It does not ingest scenario rows
and does not write to the `Anomalies` table.

For each row, the actual label is compared with the predicted anomaly flag:

- Actual anomaly: `label == "anomalous"`
- Predicted anomaly: maximum detector score is greater than or equal to the
  active threshold
- Default threshold: `2.5`, matching `Config.Z_LOW`
- Severity labels use the existing Phase 6 severity bands

This means the evaluation is based on labelled ground truth row by row, not on
dashboard totals or stored anomaly counts.

## Per-Scenario Results

### Normal labelled scenario

| TP | FP | TN | FN |
|---:|---:|---:|---:|
| 0 | 1 | 69 | 0 |

Metrics:

| Precision | Recall | F1 | False-positive rate | Predicted anomalies |
|---:|---:|---:|---:|---:|
| 0.0000 | 0.0000 | 0.0000 | 0.0143 | 1 |

Interpretation: this scenario contains no labelled anomalies, so recall and F1
are not meaningful as success measures here. The important result is the
false-positive rate: 1 out of 70 normal records was flagged. The false positive
was a normal `U002` record at `05:10`, flagged for an abnormal login-time score
of `3.23`.

### After-hours labelled scenario

| TP | FP | TN | FN |
|---:|---:|---:|---:|
| 28 | 0 | 42 | 0 |

Metrics:

| Precision | Recall | F1 | False-positive rate | Predicted anomalies |
|---:|---:|---:|---:|---:|
| 1.0000 | 1.0000 | 1.0000 | 0.0000 | 28 |

Interpretation: the detector identifies the after-hours login scenario very
strongly. This is expected because login-time deviations are directly modelled
with per-user Z-scores.

### Exfiltration/resource/access-spike labelled scenario

| TP | FP | TN | FN |
|---:|---:|---:|---:|
| 23 | 2 | 40 | 5 |

Metrics:

| Precision | Recall | F1 | False-positive rate | Predicted anomalies |
|---:|---:|---:|---:|---:|
| 0.9200 | 0.8214 | 0.8679 | 0.0476 | 25 |

Interpretation: the detector performs well but not perfectly on exfiltration.
It misses 5 labelled anomalies, mostly where the access-count increase or
resource rarity score remains below the configured threshold. It also flags 2
normal records in this scenario, both due to access-count deviation.

Missed labelled anomalies:

| Row | User | Reason | Score |
|---:|---|---|---:|
| 4 | U010 | Rare resource_type | 1.821 |
| 16 | U011 | Abnormal access_count | 1.493 |
| 31 | U007 | Abnormal access_count | 1.907 |
| 45 | U017 | Abnormal login_time | 0.851 |
| 50 | U015 | Abnormal access_count | 1.418 |

## Combined Results

| TP | FP | TN | FN |
|---:|---:|---:|---:|
| 51 | 3 | 151 | 5 |

Combined metrics:

| Total records | Labelled anomalies | Predicted anomalies | Precision | Recall | F1 | False-positive rate |
|---:|---:|---:|---:|---:|---:|---:|
| 210 | 56 | 54 | 0.9444 | 0.9107 | 0.9273 | 0.0195 |

## Threshold Sensitivity

The table below evaluates alternate score thresholds without changing the
detector scoring constants. It shows the expected trade-off: lower thresholds
increase sensitivity but create more false positives; higher thresholds reduce
false positives but miss more labelled anomalies.

| Threshold | Precision | Recall | F1 | False-positive rate | Predicted anomalies |
|---:|---:|---:|---:|---:|---:|
| 2.0 | 0.7969 | 0.9107 | 0.8500 | 0.0844 | 64 |
| 2.5 | 0.9444 | 0.9107 | 0.9273 | 0.0195 | 54 |
| 3.0 | 0.9804 | 0.8929 | 0.9346 | 0.0065 | 51 |
| 3.5 | 1.0000 | 0.8214 | 0.9020 | 0.0000 | 46 |
| 4.0 | 1.0000 | 0.8214 | 0.9020 | 0.0000 | 46 |

## Strengths

- The detector is highly effective for clear after-hours login behaviour.
- Combined false-positive rate remains low at the configured threshold.
- Row-level explanations identify the responsible feature for every scored
  record.
- Evaluation is isolated from the demo anomaly store, preserving the calibrated
  Phase 8 database state.

## Weaknesses

- Subtle exfiltration-like records can fall below the configured threshold when
  their access-count spike is moderate or the resource is rare but not unseen.
- The all-normal scenario still produces a small number of false positives.
- A single maximum-feature score is interpretable, but it does not combine weak
  signals across login time, access count, and resource rarity.

## Limitations

- The labelled scenarios are synthetic and deterministic; they are useful for
  artefact validation but do not prove performance on real organisational data.
- Labels are scenario-level ground truth created by the generator, not human
  analyst adjudications.
- The evaluation uses the latest available per-user baseline; baseline drift,
  retraining cadence, and seasonal behaviour are outside this phase.
- Accuracy is deliberately not used as the headline metric because the labelled
  data is imbalanced and anomaly detection cares more about recall, precision,
  and false-positive rate.

## AT3/AT4 Meaning

For AT3, Phase 9 demonstrates that the detector can be evaluated against
labelled ground-truth rows using measurable, reproducible metrics. This supports
Objective 4 by showing detection rate, false-positive behaviour, precision, F1,
and threshold sensitivity rather than relying on dashboard counts.

For AT4, the results provide evidence for reflective discussion: the artefact is
strong for obvious temporal anomalies, good but imperfect for exfiltration-style
behaviour, and limited where anomalous intent appears only as moderate movement
within a user's normal statistical range.
