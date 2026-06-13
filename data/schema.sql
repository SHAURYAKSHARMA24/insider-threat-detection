-- Insider Threat Detection System -- relational schema (AT2 Table 3.4).
-- Engine: SQLite.
-- NOTE: SQLite does not enforce foreign keys unless enabled per connection:
--       PRAGMA foreign_keys = ON;   (run by app/db.py in Phase 2)

PRAGMA foreign_keys = ON;

-- Users: one row per monitored user.
CREATE TABLE IF NOT EXISTS Users (
    user_id   TEXT PRIMARY KEY,
    user_name TEXT NOT NULL,
    user_role TEXT
);

-- ActivityLogs: structured activity records ingested from CSV (FR1, FR2).
CREATE TABLE IF NOT EXISTS ActivityLogs (
    log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT    NOT NULL,
    login_time    TEXT    NOT NULL,   -- HH:MM (24-hour clock)
    access_count  INTEGER NOT NULL,
    resource_type TEXT    NOT NULL,
    activity_date TEXT    NOT NULL,   -- ISO date YYYY-MM-DD
    FOREIGN KEY (user_id) REFERENCES Users (user_id)
);

-- Baselines: per-user statistical baseline (FR3 / Objective 2).
CREATE TABLE IF NOT EXISTS Baselines (
    baseline_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                    TEXT NOT NULL,
    average_login_time         REAL NOT NULL,  -- mean login hour (0-24)
    sd_login_time              REAL NOT NULL,  -- standard deviation of login hour
    average_access_count       REAL NOT NULL,  -- mean daily access count
    sd_access_count            REAL NOT NULL,  -- standard deviation of access count
    common_resource_type       TEXT,           -- modal resource type for the user
    resource_distribution_json TEXT,           -- JSON {resource_type: probability} for categorical rarity scoring (FR4)
    baseline_period            TEXT,           -- description of the window used to build the baseline
    FOREIGN KEY (user_id) REFERENCES Users (user_id)
);

-- Anomalies: flagged records with severity and explainable reason (FR5 / FR6 / NFR1).
CREATE TABLE IF NOT EXISTS Anomalies (
    anomaly_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT    NOT NULL,
    log_id              INTEGER NOT NULL,
    deviation_score     REAL    NOT NULL,  -- max |Z| (or rarity-equivalent) for the record
    severity_level      TEXT    NOT NULL,  -- 'Low' | 'Medium' | 'High'
    anomaly_reason      TEXT    NOT NULL,  -- e.g. "Abnormal login time, Z = 3.2"
    detection_timestamp TEXT    NOT NULL,  -- ISO timestamp when the record was flagged
    FOREIGN KEY (user_id) REFERENCES Users (user_id),
    FOREIGN KEY (log_id)  REFERENCES ActivityLogs (log_id)
);
