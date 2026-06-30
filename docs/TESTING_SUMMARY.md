# Testing & Evaluation Summary

How the artefact is verified: an automated test suite covering behaviour, integration,
and security, plus a labelled-scenario evaluation that reports detection quality. Run
both with:

```powershell
pytest                     # full suite
python -m app.evaluation   # labelled metrics + evidence files
```

## Test suite

`pytest.ini` sets `testpaths = tests` and `pythonpath = .`. The suite uses a separate
database (`TestingConfig`) so it never touches demo data. As committed it is **115
tests, all passing**.

| Test file | Tests | Focus |
|---|---|---|
| `test_scoring.py` | 22 | Z-score, calibrated rarity, responsible feature, tie-breaks, non-finite guards |
| `test_anomalies.py` | 18 | Severity classification, storage, transactions, batch processing |
| `test_ingest.py` | 14 | Row validation, rejection reasons, parameterised inserts, transactions |
| `test_routes.py` | 14 | Endpoints, filtering, CSV export, SQL-injection safety |
| `test_baseline.py` | 13 | Per-user statistics, `MIN_RECORDS` gate, deterministic distribution |
| `test_data_generation.py` | 10 | Deterministic output, schema, row counts, label validity |
| `test_db.py` | 7 | Connection config, foreign-key pragma, schema creation |
| `test_evaluation.py` | 6 | Confusion matrix, metrics, zero-division handling, threshold sweep |
| `test_dashboard.py` | 4 | Dashboard route and rendering |
| `test_evaluation_cli.py` | 4 | Evaluation CLI output and evidence files |
| `test_app_factory.py` | 3 | Application factory, `/health`, blueprint registration |
| **Total** | **115** | |

### Coverage areas

| Area | Examples |
|---|---|
| Behavioural / unit | Pure scoring math, severity bands, baseline statistics |
| Integration | Ingest -> baseline -> score -> store against a temp database |
| Security | SQL-injection attempts via filters; output via `textContent` |
| Evaluation | Metric correctness and clean zero-division handling |
| Determinism | Byte-identical generation and stable tie-breaking |

## Evaluation methodology

`app/evaluation.py` scores three labelled scenario CSVs (`scenario_normal`,
`scenario_after_hours`, `scenario_exfiltration`) **in memory** against the persisted
per-user baselines. It performs no ingestion and no anomaly storage, so the evaluation
is isolated from the stored `Anomalies` table -- a held-out test rather than a re-score
of the training history.

For each row it compares the predicted anomaly (deviation score >= threshold) against
the ground-truth `label`, builds a confusion matrix, and computes precision, recall,
F1, and false-positive rate, plus a sensitivity sweep over thresholds 2.0 / 2.5 / 3.0 /
3.5 / 4.0.

### Headline results (default threshold 2.5)

210 records, 56 labelled anomalies:

| Metric | Value |
|---|---|
| Precision | 0.9444 |
| Recall | 0.9107 |
| F1 | 0.9273 |
| False-positive rate | 0.0195 |

Per-scenario, the `after_hours` scenario is detected perfectly, while five
`exfiltration` anomalies are missed -- a direct consequence of single-strongest-feature
scoring (see [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md)). The all-normal scenario has
no labelled anomalies, so its precision/recall/F1 are not meaningful (reported as
zero by the CLI, described as N/A in the report).

### Reproducibility

`python -m app.evaluation` prints the report and writes:

- `evidence/metrics.json` -- machine-readable results.
- `evidence/evaluation_output.txt` -- the printed report.

The discussion in [evaluation-report.md](evaluation-report.md) is derived from this
generated output, so the headline numbers are reproducible, not hand-transcribed. CI
runs the same evaluation on every push.

## Related documents

- [evaluation-report.md](evaluation-report.md) -- full per-scenario discussion.
- [evidence-index.md](evidence-index.md) -- index of generated evidence artefacts.
- [DETECTION_ENGINE.md](DETECTION_ENGINE.md) -- the scoring under test.
