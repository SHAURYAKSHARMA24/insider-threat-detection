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

Generate and rebuild:

```powershell
python data/generate_data.py
python -m app.ingest
python -m app.baseline
python -m app.anomalies
```

Run app:

```powershell
python run.py
```

Run tests:

```powershell
pytest -q
```

Run evaluation interactively:

```python
from pathlib import Path
from app.config import Config
from app.evaluation import run_scenario, confusion_matrix, metrics, threshold_sensitivity

scenario_files = [
    Path("data/scenario_normal.csv"),
    Path("data/scenario_after_hours.csv"),
    Path("data/scenario_exfiltration.csv"),
]

combined = []
for scenario_file in scenario_files:
    rows = run_scenario(scenario_file, db_path=Config.DB_PATH)
    combined.extend(rows)
    print(scenario_file.name, confusion_matrix(rows), metrics(rows))

print(confusion_matrix(combined))
print(metrics(combined))
print(threshold_sensitivity(combined))
```

## Dashboard And API Evidence

| Action | Evidence |
|---|---|
| Health check | `GET /health` |
| Dashboard | `GET /` |
| Summary totals | `GET /api/summary` |
| All anomalies | `GET /api/anomalies` |
| Severity filter | `GET /api/anomalies?severity=High` |
| User filter | `GET /api/anomalies?user=U017` |

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
| Evaluate labelled scenarios | `app/evaluation.py`, `tests/test_evaluation.py`, `docs/evaluation-report.md` |
| Preserve synthetic-data-only scope | `data/generate_data.py`, `data/data-dictionary.md` |

## Limitations And Deferred Items

- No real organisational data is used.
- No authentication or role-based access control is implemented.
- No real-time streaming pipeline is implemented.
- No deployment or cloud infrastructure is included.
- No pagination, charts, CSV export, or report export is implemented.
- FR10 must remain deferred unless an actual CSV export feature is added later.
- Exfiltration detection can miss subtle cases where feature scores remain below
  threshold.
