# Code Walkthrough Map

## System Flow

```text
data/generate_data.py
  -> data/*.csv
  -> app/ingest.py
  -> SQLite tables from data/schema.sql
  -> app/baseline.py
  -> app/scoring.py
  -> app/anomalies.py
  -> app/routes.py
  -> dashboard UI
  -> app/evaluation.py for labelled scenario evidence
```

## Key Files

| Area | File | What to explain |
|---|---|---|
| Synthetic data | `data/generate_data.py` | Deterministic baseline and labelled scenarios |
| Data dictionary | `data/data-dictionary.md` | Field meaning and scenario purpose |
| Schema | `data/schema.sql` | Users, ActivityLogs, Baselines, Anomalies |
| DB access | `app/db.py` | SQLite connection, row factory, foreign keys, app teardown |
| Ingestion | `app/ingest.py` | CSV loading, validation, rejected rows, parameterised inserts |
| Baselines | `app/baseline.py` | Per-user mean, standard deviation, resource distribution |
| Scoring | `app/scoring.py` | Z-score features, resource rarity, responsible feature |
| Anomaly storage | `app/anomalies.py` | Severity bands and stored explanations |
| Flask routes | `app/routes.py` | Dashboard route, `/api/summary`, `/api/anomalies` filters |
| Dashboard | `app/templates/dashboard.html` | Main dashboard shell |
| Dashboard JS | `app/static/js/dashboard.js` | API consumption and filtering UI behaviour |
| Dashboard CSS | `app/static/css/styles.css` | Presentation only |
| Evaluation | `app/evaluation.py` | Row-level labelled evaluation and threshold sensitivity |
| Evaluation tests | `tests/test_evaluation.py` | Confusion matrix, metrics, isolation regression |

## Requirement-To-Code Map

| Requirement / objective | Evidence |
|---|---|
| FR1 ingestion | `app/ingest.py`, `tests/test_ingest.py` |
| FR2 relational store | `data/schema.sql`, `app/db.py`, `tests/test_db.py` |
| FR3 per-user baselines | `app/baseline.py`, `tests/test_baseline.py` |
| FR4 anomaly scoring | `app/scoring.py`, `tests/test_scoring.py` |
| FR5 configurable thresholds | `app/config.py`, `app/anomalies.py` |
| FR6 severity labels | `app/anomalies.py`, `tests/test_anomalies.py` |
| FR7 summary/API view | `app/routes.py`, `tests/test_routes.py` |
| FR8 dashboard/filtering | `app/templates/dashboard.html`, `app/static/js/dashboard.js`, `tests/test_dashboard.py` |
| FR9 / Objective 4 evaluation | `app/evaluation.py`, `tests/test_evaluation.py`, `docs/evaluation-report.md` |
| NFR1 explainability | `app/scoring.py`, `Anomalies.anomaly_reason`, dashboard row detail |
| NFR2 synthetic data only | `data/generate_data.py`, `data/*.csv` |
| FR10 CSV export | Not implemented; do not present as complete |

## Walkthrough Narrative

Start with the data generator to establish that the artefact is synthetic and
reproducible. Move to ingestion and schema to show data quality and relational
storage. Then explain baselines and scoring as the core detection logic. After
that, show anomaly storage and API/dashboard presentation. Finish with
evaluation because it proves the detector against labelled rows rather than
just showing that anomalies exist.

## Testing Map

| Test file | Coverage |
|---|---|
| `tests/test_data_generation.py` | Deterministic synthetic data and scenario shape |
| `tests/test_db.py` | Schema creation and DB behaviour |
| `tests/test_ingest.py` | CSV validation and safe insertion |
| `tests/test_baseline.py` | Baseline calculations and eligible users |
| `tests/test_scoring.py` | Z-score, rarity, responsible feature |
| `tests/test_anomalies.py` | Severity labels and anomaly persistence |
| `tests/test_routes.py` | API summary and anomaly filtering |
| `tests/test_dashboard.py` | Dashboard route and UI assets |
| `tests/test_evaluation.py` | Confusion matrix, metrics, threshold sensitivity, DB isolation |
