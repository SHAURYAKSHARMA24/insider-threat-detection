# AT3 Demo Script

## Timing Plan

Use this as a 15-minute structure:

| Segment | Time | Focus |
|---|---:|---|
| Introduction | 1 min | Aim, scope, synthetic-data constraint |
| Software demo | 7 min | Dashboard, API evidence, anomaly explanations |
| Code walkthrough | 7 min | Data flow, baselines, scoring, storage, evaluation |
| Conclusion | 1 min | Results, limitations, next phase |

## Opening

This artefact is an explainable behaviour-based insider-threat detector built
for COM668 AT3. It uses synthetic activity data only. The system builds
per-user behavioural baselines, scores new activity with Z-score and calibrated
resource-rarity logic, stores severity-labelled anomalies, exposes JSON APIs,
and displays results in a Flask dashboard.

The key exclusions are also intentional: no machine learning, no authentication,
no deployment layer, and no real-time monitoring.

## Demo Command Sequence

From the project root (one-command rebuild, then start the app):

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/rebuild.py
python run.py
```

Open:

```text
http://127.0.0.1:5000/
http://127.0.0.1:5000/health
http://127.0.0.1:5000/api/summary
http://127.0.0.1:5000/api/anomalies
http://127.0.0.1:5000/api/anomalies?severity=High
http://127.0.0.1:5000/api/anomalies.csv?severity=High
```

Run tests:

```powershell
pytest -q
```

If pytest cannot write to the default Windows temp directory, use the local
workspace temp path:

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TMP=(Resolve-Path .tmp).Path
$env:TEMP=(Resolve-Path .tmp).Path
.\.venv\Scripts\python.exe -m pytest -q -o cache_dir=.tmp\.pytest_cache --basetemp=.tmp\pytest
```

Run labelled evaluation (prints the report and saves the evidence files):

```powershell
python -m app.evaluation
```

## Seven-Minute Software Demo

1. Show `/health`.
   Confirm the Flask app is running.

2. Show `/api/summary`.
   Explain the total activity logs, total anomalies, high-risk anomaly count,
   and users monitored.

3. Show the dashboard at `/`.
   Point to summary tiles, filter controls, anomaly table, severity labels, and
   row-level explanation text.

4. Filter the dashboard or API by severity.
   Use `/api/anomalies?severity=High` to show that the backend supports
   server-side filtering with parameterised SQL.

5. Open `/api/anomalies`.
   Show that each anomaly includes user, date, login time, resource type, access
   count, deviation score, severity, and explanation.

6. Click **Download CSV** on the dashboard (FR10).
   Show that the export respects the active filters (e.g. apply Severity = High
   first), then open the saved `anomalies.csv` to show the analyst-ready output.

7. Discuss evaluation evidence.
   Use `docs/evaluation-report.md`: combined precision `0.9444`, recall
   `0.9107`, F1 `0.9273`, and false-positive rate `0.0195` at threshold `2.5`.

## Seven-Minute Code Walkthrough

1. `data/generate_data.py`
   Explain deterministic synthetic users, baseline data, and labelled scenario
   CSVs.

2. `data/schema.sql` and `app/db.py`
   Explain SQLite tables and safe connection setup.

3. `app/ingest.py`
   Explain CSV validation, rejected rows, parameterised inserts, and why labels
   are validated but not stored in `ActivityLogs`.

4. `app/baseline.py`
   Explain per-user averages, standard deviations, resource distributions, and
   minimum record threshold.

5. `app/scoring.py`
   Explain Z-score scoring for login/access and calibrated rarity for resource
   type.

6. `app/anomalies.py`
   Explain severity bands and anomaly storage.

7. `app/routes.py` and dashboard files
   Explain read-only JSON APIs and dashboard consumption.

8. `app/evaluation.py`
   Explain row-level labelled evaluation, confusion matrix, metrics, and
   threshold sensitivity without mutating the anomaly store.

## Conclusion

The artefact meets the core AT3 aim: it demonstrates an explainable,
behaviour-based insider-threat detector with reproducible synthetic data,
working APIs, a dashboard, tests, and labelled evaluation evidence. The strongest
result is after-hours detection. The honest weakness is subtle exfiltration,
where some labelled anomalies score below the threshold.
