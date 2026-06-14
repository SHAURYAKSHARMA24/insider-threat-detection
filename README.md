# Explainable Behaviour-Based Insider Threat Detection System

An academic software artefact (COM668 Computing Project, AT3) that detects anomalous
insider behaviour from structured activity data using **per-user statistical baselines**,
**Z-score deviation scoring**, configurable **severity thresholds**, and an **explainable**
web dashboard — using **synthetic data only**.

> **Status:** AT3-ready artefact. It includes deterministic synthetic data generation,
> SQLite ingestion, per-user baselines, anomaly scoring with severity labels and explainable
> reasons, Flask JSON APIs and a dashboard UI, CSV export, labelled scenario evaluation with
> reproducible metrics, an automated test suite, and continuous integration.

## Contents

- [Aim](#aim)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Setup](#setup-windows-powershell)
- [Run](#run)
- [Demo workflow (for assessors)](#demo-workflow-for-assessors)
- [Endpoints](#endpoints)
- [Testing](#testing)
- [Evaluation](#evaluation)
- [Continuous integration](#continuous-integration)
- [Manual data pipeline](#manual-data-pipeline-ingestion)
- [Screenshots](#screenshots)
- [Project structure](#project-structure)
- [AT2 traceability](#at2-traceability)
- [Limitations and scope](#limitations-and-scope)
- [Academic integrity](#academic-integrity)

## Aim

Model normal user activity (login timing, access frequency, resource-type usage), score new
activity for statistically significant deviation, flag anomalies with an explainable reason
and a severity label, and present them for analyst review.

## Features

- **Deterministic synthetic data** — reproducible activity history and labelled scenarios from
  a fixed seed (`data/generate_data.py`); no real or personal data.
- **Validated CSV ingestion** — explicit per-row validation with rejection reporting, written
  through parameterised SQL (`app/ingest.py`).
- **Relational store** — SQLite schema with four tables: `Users`, `ActivityLogs`, `Baselines`,
  `Anomalies` (`data/schema.sql`, `app/db.py`).
- **Per-user baselines** — mean/standard deviation of login hour and access count, plus the
  resource-type distribution, for every user meeting a minimum-records threshold
  (`app/baseline.py`).
- **Deviation scoring** — absolute Z-score for numeric features and a calibrated rarity score
  for the categorical resource type (`app/scoring.py`).
- **Configurable severity** — Low / Medium / High bands from thresholds defined in one place
  (`app/config.py`, `app/anomalies.py`).
- **Explainable anomalies** — each stored anomaly records the responsible feature and a
  human-readable reason (`Anomalies.anomaly_reason`).
- **Dashboard + JSON API** — summary tiles, filtering by user/date/severity, and a row-click
  detail panel, backed by read-only JSON endpoints (`app/routes.py`, `app/templates/`).
- **CSV export (FR10)** — the filtered anomaly view can be downloaded as CSV.
- **Labelled evaluation** — per-scenario and combined precision/recall/F1/false-positive rate
  plus threshold sensitivity, reproducible from one command (`app/evaluation.py`).
- **Tests and CI** — a `pytest` suite and a GitHub Actions workflow.

## Tech stack

- Python 3.11+ (developed on 3.13)
- Flask — web app + JSON API
- SQLite — relational store
- pandas / NumPy — statistics
- pytest — testing
- Git / GitHub Actions — version control + CI

By design there is **no** machine learning, authentication, real-time monitoring, role
management, or cloud deployment (consistent with the AT2 scope and exclusions). See
[Limitations and scope](#limitations-and-scope).

## Setup (Windows PowerShell)

```powershell
# From the project root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

Rebuild the demo database in one deterministic command (regenerate → ingest → baseline →
score), then start the app:

```powershell
python scripts/rebuild.py     # one-command rebuild (resets the database first)
python run.py
```

`scripts/rebuild.py` is the recommended path: ingestion is intentionally *not* idempotent, so
the script resets the database first to guarantee a correct rebuild. On the bundled synthetic
data this produces **12,092 rows ingested, 20 baselines, and 299 anomalies (256 Low / 41
Medium / 2 High)**. The equivalent manual steps are in [Manual data pipeline](#manual-data-pipeline-ingestion).

Open `http://127.0.0.1:5000/` for the dashboard.

## Demo workflow (for assessors)

A complete walkthrough from a clean checkout:

```powershell
# 1. Environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Build the deterministic demo database and start the app
python scripts/rebuild.py
python run.py
```

Then, in a browser at `http://127.0.0.1:5000/`:

1. Review the summary tiles (activity logs, anomalies, high-risk count, users monitored).
2. Set **Severity = High** and apply the filter to narrow the anomaly table.
3. Click an anomaly row to open the detail panel and read the **responsible feature** and
   **reason**.
4. Click **Download CSV** to export the currently filtered anomalies (FR10).

In a second terminal (with the virtual environment activated):

```powershell
python -m app.evaluation   # labelled scenario metrics (also writes evidence files)
pytest                     # automated test suite
```

A demo script and checklist are provided in `docs/at3-demo-script.md` and
`docs/at3-demo-checklist.md`.

## Endpoints

| Method & path | Description |
|---|---|
| `GET /` | Dashboard UI — summary tiles, filter panel, anomaly table, row-click detail |
| `GET /health` | Liveness check; returns `{"status": "ok"}` |
| `GET /api/summary` | Totals: activity logs, anomalies, high-risk anomalies, users monitored |
| `GET /api/anomalies` | Flagged anomalies as JSON; optional filters `user`, `start`, `end`, `severity` (e.g. `/api/anomalies?severity=High&start=2025-05-01`) |
| `GET /api/anomalies.csv` | The same filtered anomalies as a downloadable CSV (FR10) |

All filters are applied through parameterised SQL.

## Testing

```powershell
pytest
```

## Evaluation

Reproduce the labelled scenario evaluation and regenerate the evidence files in one command:

```powershell
python -m app.evaluation
```

This prints per-scenario confusion matrices, combined precision/recall/F1/false-positive rate,
and threshold sensitivity, and writes `evidence/metrics.json` (machine-readable) and
`evidence/evaluation_output.txt` (the printed report). The discussion in
`docs/evaluation-report.md` is derived from this generated output, so the headline numbers are
reproducible rather than hand-transcribed.

On the bundled labelled synthetic scenarios (210 records, 56 labelled anomalies), the detector
achieves a combined **precision of 0.9444, recall of 0.9107, F1 of 0.9273, and a false-positive
rate of 0.0195** at the default threshold (2.5). These figures describe the synthetic scenarios
only; see `docs/evaluation-report.md` for per-scenario results, threshold trade-offs, and an
honest discussion of where detection is weaker.

## Continuous integration

GitHub Actions (`.github/workflows/ci.yml`) runs on pushes and pull requests using Python 3.11.
The workflow installs `requirements.txt`, rebuilds the deterministic demo database with
`python scripts/rebuild.py`, runs `pytest -q`, and runs the labelled evaluation with
`python -m app.evaluation`.

## Manual data pipeline (ingestion)

`scripts/rebuild.py` runs the following steps in order. They can also be run individually:

```powershell
python data/generate_data.py     # writes data/*.csv (deterministic)
python -m app.ingest             # ingests data/activity_baseline.csv, prints a summary
python -m app.baseline           # builds per-user baselines into the Baselines table
python -m app.anomalies          # scores activity, stores flagged anomalies (clears first)
```

`python -m app.baseline` writes one row per eligible user (>= `MIN_RECORDS` activity records)
to `Baselines`; users below the threshold are excluded and logged. `python -m app.anomalies`
scores every activity record against its user's baseline and stores those at or above the
configured severity threshold (Low/Medium/High) in the `Anomalies` table.

Note: ingestion is not idempotent, so re-running these steps without first resetting the
database will duplicate `ActivityLogs` rows. Use `python scripts/rebuild.py` for a clean rebuild.

## Screenshots

Demonstration captures are stored in `screenshots/`:

| File | Shows |
|---|---|
| [`01_dashboard_overview.png`](screenshots/01_dashboard_overview.png) | Dashboard with summary tiles and the anomaly table |
| [`02_high_risk_filter.png`](screenshots/02_high_risk_filter.png) | The anomaly table filtered to High severity |
| [`03_row_detail_explanation.png`](screenshots/03_row_detail_explanation.png) | Row detail panel with responsible feature and reason |
| [`04_download_csv.png`](screenshots/04_download_csv.png) | CSV export of the filtered anomalies (FR10) |
| [`05_api_summary.png`](screenshots/05_api_summary.png) | `GET /api/summary` JSON response |
| [`06_api_anomalies_high.png`](screenshots/06_api_anomalies_high.png) | `GET /api/anomalies?severity=High` JSON response |
| [`07_evaluation_terminal.png`](screenshots/07_evaluation_terminal.png) | Labelled evaluation metrics in the terminal |
| [`08_pytest_pass.png`](screenshots/08_pytest_pass.png) | The test suite passing |

## Project structure

```
app/          Flask app factory, config, ingestion, baselines, scoring, anomalies, API routes, evaluation
data/         schema.sql, synthetic data generator, data dictionary, generated CSVs
scripts/      rebuild.py — one-command deterministic database rebuild
tests/        pytest suite
docs/         evaluation report, demo script/checklist, code-walkthrough map, evidence index
screenshots/  demonstration captures
evidence/     generated metrics, exports, and terminal output (for AT4)
instance/     SQLite database (generated at runtime; not committed)
run.py        development server entry point
```

## AT2 traceability

This artefact implements the design committed in the AT2 Challenge Definition Report:

| AT2 reference | Implemented by |
|---|---|
| FR1 ingestion | `app/ingest.py` + `data/schema.sql` (`ActivityLogs`) |
| FR2 relational store | `data/schema.sql` (four tables), `app/db.py` |
| FR3 per-user baselines (>= 20 records) | `app/baseline.py`; `MIN_RECORDS` in `app/config.py` |
| FR4 Z-score scoring | `app/scoring.py` |
| FR5 / FR6 flagging + severity bands | `app/anomalies.py`; thresholds in `app/config.py` |
| FR7 / FR8 dashboard + filtering | `app/routes.py` + `app/templates/`, `app/static/` |
| FR9 / Objective 4 scenario evaluation | `app/evaluation.py`, `docs/evaluation-report.md` |
| FR10 CSV export | `GET /api/anomalies.csv` in `app/routes.py` + dashboard **Download CSV** button |
| NFR1 explainable reason | `Anomalies.anomaly_reason` column, dashboard detail panel |
| NFR2 synthetic data only | `data/generate_data.py` |

A fuller requirement-to-code and requirement-to-test mapping is in `docs/code-walkthrough-map.md`.

## Limitations and scope

This is an academic artefact, not a production or deployed security system:

- **Synthetic data only.** All activity is generated; labels come from the scenario generator,
  not from analyst-confirmed incidents.
- **Transparent statistics, not machine learning.** This is a deliberate design choice that
  keeps every decision explainable.
- **Single strongest-signal scoring.** An anomaly is flagged on its strongest individual
  feature deviation, so behaviour that appears only as several weak signals can be missed (see
  the exfiltration scenario in `docs/evaluation-report.md`).
- **Non-deterministic timestamps.** `detection_timestamp` records wall-clock time, so the
  stored `Anomalies` table is not byte-identical between runs; the inputs, counts, scores, and
  severity labels are deterministic.
- **Out of scope (per AT2):** authentication, role management, real-time monitoring, machine
  learning, and cloud deployment.

## Academic integrity

All data is synthetic; no real or personal data is processed (AT2 NFR2).
