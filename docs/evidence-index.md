# Evidence Index

## Primary Evidence

| Evidence | Location | Use in AT3 |
|---|---|---|
| Source code | `app/`, `data/`, `tests/` | Demonstrates the implemented artefact |
| Evaluation report | `docs/evaluation-report.md` | Objective 4 labelled scenario evidence |
| Demo script | `docs/at3-demo-script.md` | 15-minute recording structure |
| Demo checklist | `docs/at3-demo-checklist.md` | Practical run-through checklist |
| Code walkthrough map | `docs/code-walkthrough-map.md` | Shows which files support which requirements |
| Test suite | `tests/` | Regression and behaviour verification |

## Commands Evidence

Generate and rebuild (one command, resets the DB first):

```powershell
python scripts/rebuild.py
```

Run app:

```powershell
python run.py
```

Run tests:

```powershell
pytest -q
```

Run evaluation (prints the report and writes `evidence/metrics.json` +
`evidence/evaluation_output.txt`):

```powershell
python -m app.evaluation
```

## Generated Evidence Files

These are produced by the commands above and committed under `evidence/`:

| File | Produced by | Contents |
|---|---|---|
| `evidence/metrics.json` | `python -m app.evaluation` | Machine-readable per-scenario + combined metrics + threshold sweep |
| `evidence/evaluation_output.txt` | `python -m app.evaluation` | The printed evaluation report |
| `evidence/anomalies_export.csv` | `GET /api/anomalies.csv` | Exported anomaly snapshot (FR10) |
| `evidence/pytest_output.txt` | `pytest -q` | Full passing test run (115 tests) |

## Dashboard And API Evidence

| Action | Evidence |
|---|---|
| Health check | `GET /health` |
| Dashboard | `GET /` |
| Summary totals | `GET /api/summary` |
| All anomalies | `GET /api/anomalies` |
| Severity filter | `GET /api/anomalies?severity=High` |
| User filter | `GET /api/anomalies?user=U017` |
| CSV export (FR10) | `GET /api/anomalies.csv?severity=High` / dashboard **Download CSV** |

## Evaluation Evidence

At threshold `2.5`, combined labelled evaluation results are:

| Metric | Result |
|---|---:|
| Total records | 210 |
| Labelled anomalies | 56 |
| Predicted anomalies | 54 |
| Precision | 0.9444 |
| Recall | 0.9107 |
| F1 | 0.9273 |
| False-positive rate | 0.0195 |

Threshold comparison:

| Threshold | Precision | Recall | F1 | False-positive rate | Interpretation |
|---:|---:|---:|---:|---:|---|
| 2.5 | 0.9444 | 0.9107 | 0.9273 | 0.0195 | Default, sensitivity-focused |
| 3.0 | 0.9804 | 0.8929 | 0.9346 | 0.0065 | Best F1, lower false positives |

The default `2.5` threshold is not globally optimal on F1. It is kept because
it preserves higher recall. Threshold `3.0` may be operationally preferable
where analyst workload and false positives matter more.

## Requirement-To-Evidence Mapping

| Requirement | Evidence |
|---|---|
| Ingest structured activity data | `app/ingest.py`, `tests/test_ingest.py` |
| Store users, logs, baselines, anomalies | `data/schema.sql`, `app/db.py` |
| Build per-user behavioural baselines | `app/baseline.py`, `tests/test_baseline.py` |
| Score deviations | `app/scoring.py`, `tests/test_scoring.py` |
| Label severity and explain anomaly reason | `app/anomalies.py`, dashboard row detail |
| Expose dashboard/API | `app/routes.py`, `app/templates/dashboard.html`, `app/static/js/dashboard.js` |
| Evaluate labelled scenarios | `app/evaluation.py`, `tests/test_evaluation.py`, `tests/test_evaluation_cli.py`, `docs/evaluation-report.md` |
| Export anomalies as CSV (FR10) | `GET /api/anomalies.csv` in `app/routes.py`, `tests/test_routes.py` |
| Preserve synthetic-data-only scope | `data/generate_data.py`, `data/data-dictionary.md` |

## Limitations And Deferred Items

- No real organisational data is used.
- No authentication or role-based access control is implemented.
- No real-time streaming pipeline is implemented.
- No deployment or cloud infrastructure is included.
- No pagination or charts are implemented (CSV export *is* implemented — FR10).
- `detection_timestamp` uses the wall-clock time of the scoring run, so the
  `Anomalies` table is not byte-identical between runs even though the inputs,
  counts, scores, and severities are fully deterministic.
- Exfiltration detection can miss subtle cases where feature scores remain below
  threshold.
