"""SQLite state: schema with ordered migrations. WAL mode because Streamlit and detached workers write at the same time."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import paths

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
    CREATE TABLE pipelines (
        name TEXT PRIMARY KEY, yaml_path TEXT NOT NULL, config_hash TEXT, archived INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, pipeline TEXT NOT NULL REFERENCES pipelines(name),
        goal_rows INTEGER NOT NULL, cap_usd REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active',
        baseline_json TEXT, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, ended_at TEXT);
    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER REFERENCES cycles(id), step_id TEXT NOT NULL,
        params_json TEXT, status TEXT NOT NULL DEFAULT 'queued',   -- queued|running|done|failed|cancelled|interrupted|paused_quota
        pid INTEGER, started_at TEXT, heartbeat_at TEXT, finished_at TEXT,
        log_path TEXT, checkpoint_path TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
        exit_code INTEGER, error TEXT);
    CREATE TABLE key_leases (
        key_prefix TEXT PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id), acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE key_status (
        key_prefix TEXT NOT NULL, provider TEXT NOT NULL, remaining REAL, cap REAL, resets TEXT,
        state TEXT NOT NULL, checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (key_prefix, provider));
    CREATE TABLE apify_runs (
        run_id TEXT PRIMARY KEY, actor TEXT NOT NULL, key_prefix TEXT NOT NULL, input_hash TEXT, dataset_id TEXT,
        job_id INTEGER REFERENCES jobs(id), status TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE spend_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, cycle_id INTEGER REFERENCES cycles(id),
        step_id TEXT, source TEXT, kind TEXT NOT NULL DEFAULT 'apify',   -- apify|tavily|llm
        key_prefix TEXT, est_max_usd REAL, actual_usd REAL, results INTEGER, note TEXT);
    CREATE TABLE stop_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER REFERENCES cycles(id), rule TEXT NOT NULL, reason TEXT,
        tripped_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, acknowledged_at TEXT);
    CREATE TABLE companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER REFERENCES cycles(id), domain TEXT NOT NULL, name TEXT, country TEXT,
        source TEXT, evidence_json TEXT, llm_json TEXT, decision TEXT NOT NULL DEFAULT 'pending',   -- pending|approved|rejected|look
        reason_code TEXT, decided_at TEXT, UNIQUE (cycle_id, domain));
    CREATE TABLE people (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER REFERENCES cycles(id), domain TEXT, fields_json TEXT NOT NULL,
        confidence TEXT, flags_json TEXT, decision TEXT NOT NULL DEFAULT 'pending', reason_code TEXT, decided_at TEXT);
    CREATE TABLE appended_rows (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER REFERENCES cycles(id), tab TEXT NOT NULL, row_number INTEGER NOT NULL,
        name TEXT, company TEXT, url TEXT, ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE known_domains (
        domain TEXT NOT NULL, pipeline TEXT NOT NULL, status TEXT NOT NULL,   -- crawled|pooled|verified|rejected
        source TEXT, first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (domain, pipeline, status));
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE INDEX idx_jobs_status ON jobs(status);
    CREATE INDEX idx_ledger_cycle ON spend_ledger(cycle_id);
    CREATE INDEX idx_companies_cycle ON companies(cycle_id);
    """),
]


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or paths.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30, isolation_level=None)   # autocommit; use `tx()` for transactions
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=30000")
    return con


@contextmanager
def tx(con: sqlite3.Connection):
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


def migrate(con: sqlite3.Connection) -> int:
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    done = {r[0] for r in con.execute("SELECT version FROM schema_migrations")}
    for version, sql in MIGRATIONS:
        if version in done:
            continue
        with tx(con):
            for stmt in [s for s in sql.split(";\n") if s.strip()]:
                con.execute(stmt)
            con.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
    return max(r[0] for r in con.execute("SELECT version FROM schema_migrations"))


def open_db(path: Path | None = None) -> sqlite3.Connection:
    con = connect(path)
    migrate(con)
    return con


def get_setting(con: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def set_setting(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
