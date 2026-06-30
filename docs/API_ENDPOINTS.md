# API Endpoints

Full specification of the HTTP routes exposed by the Flask application
(`app/__init__.py` and `app/routes.py`). All endpoints are read-only `GET` requests;
the system never mutates state over HTTP. Every filter is bound as a SQL parameter, so
unknown or malformed values produce an empty result rather than an error or an
injection vector.

Base URL during local development: `http://127.0.0.1:5000`.

## Summary

| Method & path | Auth | Returns |
|---|---|---|
| `GET /` | none | HTML dashboard shell |
| `GET /health` | none | `application/json` liveness object |
| `GET /api/summary` | none | `application/json` aggregate counts |
| `GET /api/anomalies` | none | `application/json` filtered anomaly list |
| `GET /api/anomalies.csv` | none | `text/csv` attachment of the same filtered list |

There is no authentication layer by design (out of AT2 scope).

---

## GET /

Renders `templates/dashboard.html`. The page then loads its data client-side from the
JSON endpoints below.

- **200** -- HTML document.

## GET /health

Liveness check used by tests and the live demo.

- **200** -- `{"status": "ok"}`

## GET /api/summary

Aggregate counts for the dashboard summary tiles.

**Response 200**

```json
{
  "total_activity_logs": 12092,
  "total_anomalies": 299,
  "high_risk_anomalies": 2,
  "users_monitored": 20
}
```

| Field | Meaning |
|---|---|
| `total_activity_logs` | Row count of `ActivityLogs` |
| `total_anomalies` | Row count of `Anomalies` |
| `high_risk_anomalies` | Anomalies with `severity_level = 'High'` |
| `users_monitored` | Row count of `Users` |

## GET /api/anomalies

Flagged anomalies as JSON, joined to their originating activity row and ordered by
`deviation_score` descending.

**Query parameters** (all optional, combinable):

| Parameter | Type | Effect |
|---|---|---|
| `user` | string | Exact `user_id` match |
| `start` | `YYYY-MM-DD` | Inclusive lower bound on `activity_date` |
| `end` | `YYYY-MM-DD` | Inclusive upper bound on `activity_date` |
| `severity` | `Low`/`Medium`/`High` | Exact severity band |

Missing parameters are simply not applied. Unknown values (e.g. `severity=Critical`)
match no rows and return an empty list -- never an error -- because every value is bound
as a SQL parameter.

**Example**

```
GET /api/anomalies?severity=High&start=2025-05-01
```

**Response 200**

```json
{
  "count": 2,
  "filters": { "user": null, "start": "2025-05-01", "end": null, "severity": "High" },
  "anomalies": [
    {
      "anomaly_id": 123,
      "user_id": "U019",
      "activity_date": "2025-05-14",
      "login_time": "02:11",
      "resource_type": "Confidential",
      "access_count": 140,
      "deviation_score": 7.22,
      "severity_level": "High",
      "anomaly_reason": "Abnormal login_time, Z = 7.22",
      "detection_timestamp": "2026-06-30T11:04:21"
    }
  ]
}
```

| Field | Source |
|---|---|
| `anomaly_id`, `user_id`, `deviation_score`, `severity_level`, `anomaly_reason`, `detection_timestamp` | `Anomalies` |
| `activity_date`, `login_time`, `resource_type`, `access_count` | joined `ActivityLogs` |

## GET /api/anomalies.csv

The same filtered, ordered result set as `GET /api/anomalies`, serialised as CSV for
download (FR10). Accepts the identical `user`/`start`/`end`/`severity` parameters, so
the dashboard exports exactly the analyst's current view.

- **200** -- `text/csv`, header `Content-Disposition: attachment; filename=anomalies.csv`
- Column order: `anomaly_id, user_id, activity_date, login_time, resource_type,
  access_count, deviation_score, severity_level, anomaly_reason, detection_timestamp`

The JSON and CSV endpoints share one query builder (`_anomaly_query`), guaranteeing
their filtering is byte-for-byte identical.

## Security notes

- **Parameterised SQL only.** No request value is ever string-interpolated into a
  query; `tests/test_routes.py` includes SQL-injection cases.
- **Read-only.** No route writes to the database.
- **Output escaping.** The dashboard renders values via `textContent`, not raw HTML.

## Related documents

- [ARCHITECTURE.md](ARCHITECTURE.md) -- request lifecycle and the shared query builder.
- [TESTING_SUMMARY.md](TESTING_SUMMARY.md) -- the route and security tests.
