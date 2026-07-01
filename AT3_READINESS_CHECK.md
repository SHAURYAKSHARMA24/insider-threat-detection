# AT3 Software Demonstration — Read-Only Readiness Check

**Repo:** insider-threat-detection (COM668 AT3)
**Checked:** 2026-07-01 · read-only pass, no source files modified
**Branch at check time:** `docs/readme-improvements` @ `14c7f18`

## Verdict summary

| # | Section | Verdict |
|---|---------|---------|
| 1 | Git state | **ATTENTION NEEDED** — tree is clean, but you are on `docs/readme-improvements` (not `master`), and the current commit does **not** match `v1.0.0`. |
| 2 | Deterministic rebuild | **PASS** — exact match on all counts. |
| 3 | Test suite | **PASS** — 115 passed, matches README. |
| 4 | Evaluation module | **PASS** — exact match on every scenario + combined metric. |
| 5 | Live server + API + FR7 timestamp | **PASS** — all endpoints 200; timestamp **is** shown on screen. Note: port 5000 is blocked — use 5050. |
| 6 | Code walkthrough talking points | **PASS** — all five verified, references below. |
| 7 | CERT dataset discrepancy | **PASS** — zero CERT references anywhere; no half-implemented loader. Draft explanation below. |
| 8 | On-camera hygiene | **PASS** — no TODO/FIXME/debug/secrets; `.gitignore` correct. |
| 9 | Environment sanity | **ATTENTION NEEDED** — venv matches requirements exactly, but **port 5000 is not free** on this machine. |

---

## 1. Git state — ATTENTION NEEDED

- **Working tree:** clean (`git status` → nothing to commit) — including after running rebuild + evaluation, which regenerate deterministic outputs byte-identically.
- **Current branch:** `docs/readme-improvements` @ `14c7f18`, **3 commits ahead of `master`** (`9b5ea2c`). The only difference from `master` is `README.md` (`git diff --stat master HEAD` → `README.md` only; **app/ data/ scripts/ are identical** to master).
- **`v1.0.0` tag:** does **not** exist locally (`git tag` is empty; `git describe` fails). On the remote, `v1.0.0` → `d4734d4`, which is **a different commit from both HEAD (`14c7f18`) and master (`9b5ea2c`)** and is not in your local history at all.
  - So: **"current commit matches v1.0.0" is FALSE.** The tag points at neither the branch you're on nor master.

**You must decide (see decision list at the bottom) which commit is the frozen artefact and whether/where to (re-)tag before recording.**

---

## 2. Fresh deterministic rebuild — PASS

`python scripts/rebuild.py` from a clean state (DB removed first):

```
[1/4] generating synthetic data ...
[generate] activity_baseline.csv: 12092 rows
[generate] scenario_normal.csv: 70 rows
[generate] scenario_after_hours.csv: 70 rows
[generate] scenario_exfiltration.csv: 70 rows
[2/4] ingesting baseline activity ...
        ingested 12092 rows, 20 users, 0 rejected
[3/4] building per-user baselines ...
        20 baselines built, 0 users excluded
[4/4] scoring and storing anomalies ...
        299 anomalies stored (Low 256 / Medium 41 / High 2)
```

| Metric | Quoted | Actual | Match |
|--------|-------:|-------:|:-----:|
| Rows ingested | 12,092 | 12,092 | ✅ |
| Users | 20 | 20 | ✅ |
| Baselines | 20 | 20 | ✅ |
| Anomalies total | 299 | 299 | ✅ |
| Low | 256 | 256 | ✅ |
| Medium | 41 | 41 | ✅ |
| High | 2 | 2 | ✅ |

**No mismatch.**

---

## 3. Full test suite — PASS

`pytest -q` → **`115 passed in 17.21s`**, 0 failures, 0 warnings.

Breakdown: test_anomalies 18 · test_app_factory 3 · test_baseline 13 · test_dashboard 4 · test_data_generation 10 · test_db 7 · test_evaluation 6 · test_evaluation_cli 4 · test_ingest 14 · test_routes 14 · test_scoring 22.

Matches the README "115 passing" badge (`README.md:6`) and text (`README.md:236`). **No drift.**

---

## 4. Evaluation module — PASS

`python -m app.evaluation` output (threshold 2.5):

```
Per-scenario results
scenario                      TP  FP   TN  FN     Prec     Rec      F1     FPR
scenario_normal.csv            0   1   69   0   0.0000  0.0000  0.0000  0.0143
scenario_after_hours.csv      28   0   42   0   1.0000  1.0000  1.0000  0.0000
scenario_exfiltration.csv     23   2   40   5   0.9200  0.8214  0.8679  0.0476

Combined results
  records=210  labelled_anomalies=56  predicted_anomalies=54
  precision=0.9444  recall=0.9107  f1=0.9273  false_positive_rate=0.0195
```

| Metric | docs/evaluation-report.md | Actual | Match |
|--------|--------------------------:|-------:|:-----:|
| Combined precision | 0.9444 | 0.9444 | ✅ |
| Combined recall | 0.9107 | 0.9107 | ✅ |
| Combined F1 | 0.9273 | 0.9273 | ✅ |
| Combined FPR | 0.0195 | 0.0195 | ✅ |
| after_hours P/R/F1 | 1.0/1.0/1.0 | 1.0/1.0/1.0 | ✅ |
| exfiltration P/R/F1 | 0.92/0.8214/0.8679 | 0.92/0.8214/0.8679 | ✅ |
| normal FPR | 0.0143 | 0.0143 | ✅ |

Threshold-sensitivity table also matches the report exactly (2.5 → 0.9444/0.9107/0.9273/0.0195; 3.0 → best F1 0.9346). **No drift.** (The command writes `evidence/metrics.json` and `evidence/evaluation_output.txt` — these regenerate identically, tree stays clean.)

---

## 5. Live server + API checks — PASS (with a port caveat)

**Port note:** `python run.py` on port 5000 **failed** — port 5000 is held by the Windows `System` process (PID 4), the reserved-port-range issue. All checks below were run on the **5050 fallback** and every endpoint returned **200**.

| Endpoint | Status | Response shape |
|----------|:------:|----------------|
| `GET /health` | 200 | `{"status":"ok"}` |
| `GET /` | 200 | HTML dashboard shell (`<!DOCTYPE html>…`) |
| `GET /api/summary` | 200 | `{high_risk_anomalies:2, total_activity_logs:12092, total_anomalies:299, users_monitored:20}` |
| `GET /api/anomalies` | 200 | `{count:299, filters:{…}, anomalies:[…]}` — each row has `anomaly_id, user_id, activity_date, login_time, resource_type, access_count, deviation_score, severity_level, anomaly_reason, detection_timestamp` |
| `GET /api/anomalies?severity=High` | 200 | `count:2` (U019 login_time Z=5.14; U007 access_count Z=4.02) |
| `GET /api/anomalies?user=U006` | 200 | `count:14` |
| `GET /api/anomalies.csv` | 200 | `text/csv`, attachment; header row = the 10 columns above |

### FR7 timestamp — CONFIRMED VISIBLE ON SCREEN ✅

Your FR7 ("user, timestamp, severity, deviation score, and anomaly reason") **is** satisfied on screen. The activity timestamp is rendered in two places:

- **Anomaly table** (`app/templates/dashboard.html:78`): column headers include **`Date`** and **`Login`**; rows are populated with `row.activity_date` and `row.login_time` (`app/static/js/dashboard.js:106-107`).
- **Row-click detail panel** (`app/templates/dashboard.html:97`): a **`Date / time`** field (`id="d-datetime"`) populated with `activity_date + login_time` (`app/static/js/dashboard.js:139`).

So each anomaly shows: **User** (`user_id`), **timestamp** (`activity_date` + `login_time`), **Severity** (badge), **Deviation score** (`deviation_score`), **Reason** (`anomaly_reason`) — all five FR7 fields. (A separate `detection_timestamp` is in the API/CSV but not surfaced in the UI; the behavioural activity timestamp that FR7 refers to *is* shown.)

You can safely say on camera: *"The dashboard shows the activity date and login time for every flagged record, both in the table and in the detail panel."*

---

## 6. Code walkthrough talking points — PASS (file:line references)

| Point | Where | Notes |
|-------|-------|-------|
| **a. Z-score for login_time & access_count** | `app/scoring.py:39-48` (`z_score()` def); applied at `app/scoring.py:141-145` (login_time_z) and `:146-150` (access_count_z) | `abs((value - mean) / sd)` |
| **b. Calibrated categorical rarity/surprisal for resource_type** | `app/scoring.py:51-93` (`resource_rarity()`); formula at `:91-93`; scale rationale in module docstring `:9-17` | Computes `max(0, -log(p) + log(0.05))` (reference prob 0.05, unseen floored at 0.001 ≈ 3.9). Deliberately scaled to be **comparable to a Z-score** so one threshold covers all three features. ✅ Your on-camera claim — *"extends the Z-score deviation approach to a categorical feature where Z-scores don't apply"* — is accurate and directly supported by the code + docstring. |
| **c. 999.0 sentinel for zero-SD baselines** | `app/scoring.py:26` (`SD_ZERO_DEVIATION = 999.0`); used at `:47` (`return 0.0 if value == mean else SD_ZERO_DEVIATION`) | Finite, never inf/NaN |
| **d. Severity band thresholds** | `app/config.py:22-24` and `:28` | `Z_LOW = 2.5`, `Z_MEDIUM = 3.0`, `Z_HIGH = 4.0`, `MIN_RECORDS = 20` — **all confirmed exactly.** Bands applied in `app/anomalies.py:39-45` (`classify_severity`). |
| **e. anomaly_reason = responsible feature + value (NFR1)** | `app/scoring.py:96-112` (`responsible_feature()`), `:115-121` (`build_anomaly_reason()`), set at `:171`; persisted at `app/anomalies.py:52-63` | e.g. `"Abnormal login_time, Z = 5.14"`, `"Rare resource_type, score = 2.31"` |

---

## 7. CERT dataset discrepancy check — PASS

- **Grep for `CERT` / `r4.2` / "insider threat test" across the whole repo (code, docs, README, comments, excluding `.venv`): ZERO matches.**
- No leftover CERT reference contradicting the synthetic approach, and **no half-implemented CERT loading code.**
- The repo is consistently and explicitly synthetic-only: README badges/sections (`README.md:8, 23, 45, 296, 334`), `data/generate_data.py:1-7` header ("synthetic data only … no external downloads (AT2 NFR2)", `SEED = 42`).

### Draft explanation to memorise (why CERT → custom synthetic generator)

> "My AT2 risk register flagged the CERT r4.2 dataset as a realism option, but I moved to a deterministic, seed-42 synthetic generator for the artefact. CERT r4.2 is large, licence-gated, and can't be redistributed inside an assessed submission, and it wouldn't rebuild reproducibly on a fresh clone — whereas my generator ships with the code and produces byte-identical data on every run, which is exactly what a reproducible, privacy-safe demonstration needs (NFR2, synthetic-data-only). I preserve evaluation realism instead through labelled normal, after-hours, and exfiltration scenarios with ground-truth labels."

(Trim to the first two sentences if you need it shorter on camera.)

---

## 8. Hygiene pass for on-camera code — PASS

- **TODO / FIXME / XXX / HACK / `console.log` / `pdb` / `breakpoint()`:** none anywhere (outside `.venv`).
- **`print()` in app/:** only inside CLI `main()` entrypoints (`baseline.py:181-185`, `evaluation.py:326-333`, `anomalies.py:199-203`, `ingest.py:193`) — legitimate pipeline/summary output, not stray debug prints in the web/scoring path. (`app/__init__.py:36` and `routes.py:17` are false-positive matches on "Blue**print**".) Nothing embarrassing.
- **Hard-coded local paths / secrets / passwords / API keys / tokens in `.py`:** none. `config.py` derives paths from `os.path` (`BASE_DIR`), no absolute paths committed.
- **`.gitignore`:** correctly excludes `instance/*.sqlite*` + `.db`, `__pycache__/`, `.venv/`, `venv/`, `env/`, `.pytest_cache/`, `.tmp/`. Verified via `git status --ignored`: `instance/itd.sqlite`, all `__pycache__/`, `.venv/`, `.pytest_cache/`, `.tmp/` are ignored. `instance/.gitkeep` is tracked so the folder persists; the SQLite DB is not committed.
- **instance/ regenerates cleanly:** deleting `instance/itd.sqlite` and running `scripts/rebuild.py` recreates it from scratch (299 anomalies) — confirmed in section 2.

---

## 9. Environment sanity — ATTENTION NEEDED (port only)

- **venv vs requirements.txt — exact match, no drift:** Flask 3.1.0, pandas 2.2.3, numpy 2.1.3, pytest 8.3.4. `pip check` → "No broken requirements found." Python 3.13.1.
- **Port 5000 is NOT free on this machine.** It is held by the Windows `System` process (PID 4) — a reserved TCP port range (common with Hyper-V/WSL). `python run.py` errors with *"An attempt was made to access a socket in a way forbidden by its access permissions."*
- **Fallback (verified working — all 7 endpoints returned 200 on it):**
  ```
  python -m flask --app run:app run --host 127.0.0.1 --port 5050
  ```
  Then browse **http://127.0.0.1:5050/**. Have this command ready before you hit record. (Port 5050 was confirmed free.)

---

## Things for YOU to decide/fix before the final freeze-and-rebuild

1. **Branch + tag (the one real blocker).** You are on `docs/readme-improvements`, not `master`, and the current commit does **not** match `v1.0.0` (which points at `d4734d4`, a commit not even in your local history). App/data/scripts are identical to `master`; only `README.md` differs. Decide:
   - which commit is the frozen artefact you'll record from (e.g. merge `docs/readme-improvements` → `master`, or record from `master`);
   - whether to (re)create/move a `v1.0.0` tag onto that commit and `git fetch --tags` so the tag exists locally;
   - then confirm `git status` clean immediately before recording.
   *(This is a versioning/presentation decision, not a code bug — say the word and I'll lay out the exact commands, but I won't run anything that changes git state without you.)*
2. **Use the 5050 command during recording.** Port 5000 is blocked on this machine. Either run the fallback above, or free the reserved range beforehand. Don't discover this live.
3. **Nothing else needs fixing.** Rebuild, tests (115), evaluation metrics, all API endpoints, FR7 timestamp on screen, hygiene, and environment are all green. No source change is required for the demo to be correct.

*(Optional cosmetic, not required: `.tmp/` holds old working files — `pr_body*.md`, `server*.log`. It's git-ignored, so it won't appear in the repo, but if you happen to expand that folder in your editor's file tree on camera it's visible. Collapse or ignore it while screen-sharing.)*
