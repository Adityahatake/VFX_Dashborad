"""What we already know (never re-crawl, never re-propose): domains and company names per pipeline, kept in SQLite.
Sheet companies join this set in phase 5 (when the Sheets client exists); VFX history is imported by scripts/import_vfx_history.py."""
from __future__ import annotations

import re
import sqlite3

from .textnorm import clean_domain, squash


def add_domain(con: sqlite3.Connection, pipeline: str, domain: str, status: str, source: str = "") -> None:
    d = clean_domain(domain)
    if d:
        con.execute("INSERT OR IGNORE INTO known_domains (domain, pipeline, status, source) VALUES (?,?,?,?)", (d, pipeline, status, source))


def add_domains(con: sqlite3.Connection, pipeline: str, domains, status: str, source: str = "") -> int:
    rows = [(clean_domain(d), pipeline, status, source) for d in domains if clean_domain(d)]
    con.executemany("INSERT OR IGNORE INTO known_domains (domain, pipeline, status, source) VALUES (?,?,?,?)", rows)
    return len(rows)


def add_name(con: sqlite3.Connection, pipeline: str, name: str, source: str = "") -> None:
    s = squash(name)
    if s:
        con.execute("INSERT OR IGNORE INTO known_names (name, pipeline, source) VALUES (?,?,?)", (s, pipeline, source))


def seen_domains(con: sqlite3.Connection, pipeline: str, statuses: tuple[str, ...] | None = None) -> set[str]:
    """Domains known for a pipeline, optionally only those with one of the given statuses (crawled, pooled, verified, rejected)."""
    if statuses:
        q = "SELECT DISTINCT domain FROM known_domains WHERE pipeline=? AND status IN (%s)" % ",".join("?" * len(statuses))
        return {r[0] for r in con.execute(q, (pipeline, *statuses))}
    return {r[0] for r in con.execute("SELECT DISTINCT domain FROM known_domains WHERE pipeline=?", (pipeline,))}


def known_names(con: sqlite3.Connection, pipeline: str, statuses: tuple[str, ...] | None = None) -> set[str]:
    """Squashed company names plus squashed domains: the set domain_is_known() matches against. `statuses` limits which DOMAINS count
    (names, e.g. sheet companies, always count)."""
    names = {r[0] for r in con.execute("SELECT name FROM known_names WHERE pipeline=?", (pipeline,))}
    names |= {re.sub(r"[^a-z0-9]", "", d) for d in seen_domains(con, pipeline, statuses)}
    return names - {""}
