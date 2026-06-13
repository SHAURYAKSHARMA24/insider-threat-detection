# AT3 Demo Checklist

## Before Recording

- Confirm the repository is clean enough for demonstration.
- Activate the virtual environment.
- Rebuild deterministic data if needed with `python data/generate_data.py`.
- Rebuild the demo database:

```powershell
python -m app.ingest
python -m app.baseline
python -m app.anomalies
```

- Run tests with `pytest -q`.
- Start the app with `python run.py`.
- Open `http://127.0.0.1:5000/`.

## Dashboard Actions

- Show the dashboard summary tiles.
- Show the anomaly table.
- Click an anomaly row and explain the row-level reason.
- Filter by severity in the dashboard.
- Show the API equivalent: `/api/anomalies?severity=High`.
- Show `/api/summary`.

## API Actions

Use these URLs:

```text
http://127.0.0.1:5000/health
http://127.0.0.1:5000/api/summary
http://127.0.0.1:5000/api/anomalies
http://127.0.0.1:5000/api/anomalies?severity=High
http://127.0.0.1:5000/api/anomalies?user=U017
```

Point out that the API is read-only and uses parameterised SQL filters.

## Evaluation Evidence To Mention

Default threshold `2.5`:

| Metric | Combined result |
|---|---:|
| Precision | 0.9444 |
| Recall | 0.9107 |
| F1 | 0.9273 |
| False-positive rate | 0.0195 |

Threshold comparison:

| Threshold | Precision | Recall | F1 | False-positive rate |
|---:|---:|---:|---:|---:|
| 2.5 | 0.9444 | 0.9107 | 0.9273 | 0.0195 |
| 3.0 | 0.9804 | 0.8929 | 0.9346 | 0.0065 |

Say clearly: threshold `3.0` has the best F1 and lower false-positive rate, but
threshold `2.5` remains the configured default because it preserves higher
recall and is more sensitivity-focused.

## Code Files To Open

- `data/generate_data.py`
- `data/schema.sql`
- `app/ingest.py`
- `app/baseline.py`
- `app/scoring.py`
- `app/anomalies.py`
- `app/routes.py`
- `app/evaluation.py`
- `tests/test_evaluation.py`
- `docs/evaluation-report.md`

## Limitations To State

- Data is synthetic, not real organisational data.
- Labels are generated scenario labels, not analyst-confirmed incidents.
- The detector uses transparent statistics, not machine learning.
- Subtle exfiltration can be missed when feature deviations remain below the
  threshold.
- No authentication, deployment, real-time monitoring, pagination, charts, or
  CSV export are implemented.

## Final Check

- Do not claim FR10 or CSV export is complete.
- Do not describe threshold `2.5` as globally optimal.
- Do not use accuracy as the headline evaluation metric.
- Mention precision, recall, F1, false-positive rate, and threshold sensitivity.
