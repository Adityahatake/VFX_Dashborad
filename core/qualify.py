"""Automatic company checks after the evidence crawl (SOP 01 s25 / s36 machine checks, in the strict, conservative direction).

A crawl hit is evidence that AI wording sits next to a client cue on the company's OWN site. That is necessary, not sufficient, so:
  - hard fails (press / platform site, rejected name or type, excluded country)    -> 'rejected', reason AUTO_REJECT:<why>
  - evidence score below the threshold                                             -> 'look'     (HOLD: a human or a later pass decides)
  - everything else                                                                 -> 'approved', reason AUTO_PASS
Only companies still 'pending' are touched: a human decision is never overwritten. Every decision can be changed in Review."""
from __future__ import annotations

import json
import re
import sqlite3

from .config import PipelineConfig
from .steps.discover import non_company
from .textnorm import squash

AUTO_PASS, AUTO_HOLD, AUTO_REJECT = "AUTO_PASS", "AUTO_HOLD", "AUTO_REJECT"


def check(cfg: PipelineConfig, domain: str, name: str, country: str, evidence: dict, min_score: int) -> tuple[str, str]:
    """(decision, reason_code) for one company."""
    why = non_company(domain)
    if why:
        return "rejected", f"{AUTO_REJECT}:{why}"
    blob = f"{domain} {name}"
    if any(squash(n) and squash(n) in squash(blob) for n in cfg.icp.reject_names):
        return "rejected", f"{AUTO_REJECT}:rejected company name"
    rx = re.compile("|".join(cfg.countries.excluded_patterns), re.I) if cfg.countries.excluded_patterns else None
    if rx and (rx.search(domain) or rx.search(country or "")):
        return "rejected", f"{AUTO_REJECT}:excluded country"
    if (evidence.get("score") or 0) < min_score:
        return "look", f"{AUTO_HOLD}:evidence score {evidence.get('score') or 0} < {min_score}"
    return "approved", AUTO_PASS


def qualify_cycle(con: sqlite3.Connection, cfg: PipelineConfig, cycle_id: int, min_score: int = 2, source_prefix: str | None = None) -> dict:
    """Decide every still-pending company of the cycle (optionally only those whose source starts with `source_prefix`)."""
    q, a = "SELECT * FROM companies WHERE cycle_id=? AND decision='pending'", [cycle_id]
    if source_prefix:
        q, a = q + " AND source LIKE ?", a + [source_prefix + "%"]
    counts = {"approved": 0, "look": 0, "rejected": 0}
    for r in con.execute(q, a).fetchall():
        dec, code = check(cfg, r["domain"], r["name"] or "", r["country"] or "", json.loads(r["evidence_json"] or "{}"), min_score)
        con.execute("UPDATE companies SET decision=?, reason_code=?, decided_at=CURRENT_TIMESTAMP WHERE id=? AND decision='pending'", (dec, code, r["id"]))
        counts[dec] += 1
    return counts
