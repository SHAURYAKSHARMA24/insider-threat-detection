# Explainable Behaviour-Based Insider Threat Detection System

An academic software artefact (COM668 Computing Project, AT3) that detects anomalous
insider behaviour from structured activity data using **per-user statistical baselines**,
**Z-score deviation scoring**, configurable **severity thresholds**, and an **explainable**
web dashboard.

> **Status:** AT3-ready artefact. The project includes deterministic synthetic data
> generation, SQLite ingestion, per-user baselines, anomaly scoring and severity labels,
> Flask JSON APIs, a dashboard UI, labelled scenario evaluation evidence, tests, and CI.

## Aim

Model normal user activity (login timing, access frequency, resource-type usage), score new
activity for statistically significant deviation, flag anomalies with an explainable reason
and severity label, and present them for analyst review — using **synthetic data only**.

## Tech stack

- Python 3.11+ (developed on 3.13)
- Flask — web app + JSON API
- SQLite — relational store
- Pandas / NumPy — statistics
- pytest — testing
- Git — version control

By design there is **no** machine learning, authentication, real-time monitoring, role
management, or cloud deployment (consistent with the AT2 scope and exclusions).

## Setup (Windows PowerShell)

```powershell
# From the project root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

Rebuild the whole demo database in one command (regenerate → ingest → baseline →
score), then start the app:

```powershell
python scripts/rebuild.py     # one-command, deterministic rebuild (resets the DB first)
python run.py
```

`scripts/rebuild.py` is the recommended path: ingestion is intentionally *not*
idempotent, so it resets the database first to guarantee a correct rebuild
(12,092 rows ingested, 20 baselines, 299 anomalies: 256 Low / 41 Medium / 2 High).
The equivalent manual steps are shown under [Load data](#load-data-ingestion).

Open `http://127.0.0.1:5000/` for the main dashboard demo.

Secondary health check: `http://127.0.0.1:5000/health` returns `{"status": "ok"}`.

Endpoints:

- `GET /` — dashboard UI (summary tiles, filter panel, anomaly table, row-click detail)
- `GET /api/summary` — total logs, total anomalies, high-risk count, users monitored
- `GET /api/anomalies` — flagged anomalies as JSON; optional filters `user`, `start`, `end`,
  `severity` (e.g. `/api/anomalies?severity=High&start=2025-05-01`)
- `GET /api/anomalies.csv` — the same filtered anomalies as a downloadable CSV (FR10);
  the dashboard's **Download CSV** button hits this endpoint with the active filters

## Test

```powershell
pytest
```

## CI

GitHub Actions runs on pushes and pull requests using Python 3.11. The workflow
installs `requirements.txt`, rebuilds the deterministic demo database, and runs
`pytest -q`.

## Evaluation

Reproduce the labelled scenario evaluation and write the evidence files in one
command:

```powershell
python -m app.evaluation
```

This prints per-scenario confusion matrices, combined precision/recall/F1/
false-positive rate, and threshold sensitivity, and saves `evidence/metrics.json`
(machine-readable) and `evidence/evaluation_output.txt` (the printed report). The
discussion in `docs/evaluation-report.md` is derived from this generated output,
so the headline numbers are reproducible rather than hand-transcribed.

## Load data (ingestion)

Generate the synthetic CSVs, then ingest the baseline dataset into the SQLite database
(`instance/itd.sqlite`). Ingestion creates the schema if needed, validates every row, and
inserts users and activity records:

```powershell
python data/generate_data.py     # writes data/*.csv (deterministic)
python -m app.ingest             # ingests data/activity_baseline.csv, prints a summary
python -m app.baseline           # builds per-user baselines into the Baselines table
python -m app.anomalies          # scores activity, stores flagged anomalies (clears first)
```

`python -m app.baseline` writes one row per eligible user (>= `MIN_RECORDS` activity records)
to `Baselines`; users below the threshold are excluded and logged. `python -m app.anomalies`
scores every activity record against its user's baseline and stores those at or above the
severity threshold (Low/Medium/High) in the `Anomalies` table.

## Project structure

```
app/          Flask app factory, configuration, ingestion, baselines, scoring, APIs, evaluation
data/         schema.sql, synthetic data generator, data dictionary, CSVs
tests/        pytest suite
docs/         architecture notes, evaluation report, demo script
screenshots/  demo + evidence captures
evidence/     metrics, exports, terminal logs (for AT4)
instance/     SQLite database (generated at runtime; not committed)
```

## AT2 traceability

This artefact implements the design committed in the AT2 Challenge Definition Report:

| AT2 reference | Implemented by |
|---|---|
| FR1 ingestion | `data/schema.sql` (ActivityLogs) + `app/ingest.py` (Phase 3) |
| FR2 relational store | `data/schema.sql` (4 tables) |
| FR3 per-user baselines (>=20 records) | `app/baseline.py` (Phase 4); `MIN_RECORDS` in `app/config.py` |
| FR4 Z-score scoring | `app/scoring.py` (Phase 5) |
| FR5 / FR6 flagging + severity bands | `app/scoring.py`; thresholds in `app/config.py` |
| FR7 / FR8 dashboard + filtering | `app/routes.py` + templates (Phases 7-8) |
| FR9 / Objective 4 scenario evaluation | `app/evaluation.py` (Phase 9) |
| FR10 CSV export | `GET /api/anomalies.csv` in `app/routes.py` + dashboard **Download CSV** button |
| NFR1 explainable reason | `Anomalies.anomaly_reason` column |
| NFR2 synthetic data only | `data/generate_data.py` (Phase 1) |

## Academic integrity

All data is synthetic; no real or personal data is processed (AT2 NFR2).
