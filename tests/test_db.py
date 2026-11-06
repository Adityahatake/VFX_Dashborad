import sqlite3

import pytest

from core.db import MIGRATIONS, get_setting, open_db, set_setting, tx


def test_migrate_is_idempotent(tmp_path):
    p = tmp_path / "t.sqlite"
    con = open_db(p)
    open_db(p)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ["pipelines", "cycles", "jobs", "key_leases", "key_status", "apify_runs", "spend_ledger", "stop_events",
              "companies", "people", "appended_rows", "known_domains", "settings", "schema_migrations"]:
        assert t in tables
    assert con.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(MIGRATIONS)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_one_lease_per_key(tmp_path):
    con = open_db(tmp_path / "t.sqlite")
    con.execute("INSERT INTO jobs (step_id) VALUES ('a')")
    con.execute("INSERT INTO jobs (step_id) VALUES ('b')")
    con.execute("INSERT INTO key_leases (key_prefix, job_id) VALUES ('apify_abc', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO key_leases (key_prefix, job_id) VALUES ('apify_abc', 2)")


def test_tx_rolls_back(tmp_path):
    con = open_db(tmp_path / "t.sqlite")
    with pytest.raises(RuntimeError):
        with tx(con):
            set_setting(con, "k", "v")
            raise RuntimeError
    assert get_setting(con, "k") is None


def test_settings_roundtrip(tmp_path):
    con = open_db(tmp_path / "t.sqlite")
    set_setting(con, "k", "1")
    set_setting(con, "k", "2")
    assert get_setting(con, "k") == "2"
    assert get_setting(con, "missing", "d") == "d"
