"""Spend ledger, per-cycle totals, and the stop rules. LLM spend is tracked separately (kind='llm') with its own cap."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import keys as keymod
from .config import PipelineConfig, effective_cap

MIN_DECIDED_FOR_PASS_RATE = 20      # below this the pass rate is noise, so the rule does not fire


def record(con: sqlite3.Connection, *, cycle_id: int | None, step_id: str, source: str, kind: str = "apify", key_prefix: str | None = None,
           est_max_usd: float = 0.0, actual_usd: float = 0.0, results: int = 0, note: str = "") -> int:
    return con.execute("INSERT INTO spend_ledger (cycle_id, step_id, source, kind, key_prefix, est_max_usd, actual_usd, results, note) VALUES (?,?,?,?,?,?,?,?,?)",
                       (cycle_id, step_id, source, kind, key_prefix, est_max_usd, actual_usd, results, note)).lastrowid


def _sum(con, where: str, args: tuple = ()) -> float:
    return round(con.execute(f"SELECT COALESCE(SUM(actual_usd),0) FROM spend_ledger WHERE {where}", args).fetchone()[0], 4)


def cycle_spend(con, cycle_id: int) -> float:
    """Apify + Tavily spend (everything except LLM)."""
    return _sum(con, "cycle_id=? AND kind!='llm'", (cycle_id,))


def llm_spend(con, cycle_id: int) -> float:
    return _sum(con, "cycle_id=? AND kind='llm'", (cycle_id,))


def today_spend(con) -> float:
    return _sum(con, "date(ts)=date('now') AND kind!='llm'")


def by_source(con, cycle_id: int | None = None) -> list[sqlite3.Row]:
    w, a = ("WHERE cycle_id=?", (cycle_id,)) if cycle_id else ("", ())
    return con.execute(f"SELECT source, kind, COUNT(*) AS calls, SUM(actual_usd) AS usd, SUM(results) AS results FROM spend_ledger {w} GROUP BY source, kind ORDER BY usd DESC", a).fetchall()


def reserved(con, cycle_id: int) -> float:
    """Worst-case cost of paid jobs that are queued or running (their actual spend is not in the ledger yet)."""
    return round(con.execute("SELECT COALESCE(SUM(est_max_usd),0) FROM jobs WHERE cycle_id=? AND status IN ('queued','running')", (cycle_id,)).fetchone()[0], 4)


def remaining_cap(con, cycle_id: int) -> float:
    cap = con.execute("SELECT cap_usd FROM cycles WHERE id=?", (cycle_id,)).fetchone()[0]
    return round(cap - cycle_spend(con, cycle_id) - reserved(con, cycle_id), 4)


def rows_appended(con, cycle_id: int) -> int:
    return con.execute("SELECT COUNT(*) FROM appended_rows WHERE cycle_id=?", (cycle_id,)).fetchone()[0]


def rows_approved(con, cycle_id: int) -> int:
    return con.execute("SELECT COUNT(*) FROM people WHERE cycle_id=? AND decision='approved'", (cycle_id,)).fetchone()[0]


def pass_rate(con, cycle_id: int) -> tuple[float | None, int]:
    """(approved / decided, decided) over the cycle's reviewed people; None until enough have been decided."""
    d = con.execute("SELECT COUNT(*) FROM people WHERE cycle_id=? AND decision IN ('approved','rejected')", (cycle_id,)).fetchone()[0]
    if d < MIN_DECIDED_FOR_PASS_RATE:
        return None, d
    return rows_approved(con, cycle_id) / d, d


def cost_per_row(con, cycle_id: int) -> float | None:
    rows = max(rows_appended(con, cycle_id), rows_approved(con, cycle_id))
    return round(cycle_spend(con, cycle_id) / rows, 4) if rows else None


def create_cycle(con, cfg: PipelineConfig, goal_rows: int, requested_cap: float | None) -> int:
    return con.execute("INSERT INTO cycles (pipeline, goal_rows, cap_usd) VALUES (?,?,?)", (cfg.name, goal_rows, effective_cap(cfg, requested_cap))).lastrowid


@dataclass
class Trip:
    rule: str
    reason: str


def evaluate_stop_rules(con, cfg: PipelineConfig, cycle_id: int, floor: float | None = None) -> list[Trip]:
    """Which stop rules are currently tripped for this cycle (VFX CLAUDE.md: cost/row, pass rate, usable credit, two low-yield cycles)."""
    sr, trips = cfg.budget.stop_rules, []
    cpr = cost_per_row(con, cycle_id)
    if cpr is not None and cpr > sr.max_cost_per_row:
        trips.append(Trip("cost_per_row", f"cost per final row is ${cpr:.2f}, above ${sr.max_cost_per_row:.2f}"))
    pr, decided = pass_rate(con, cycle_id)
    if pr is not None and pr < sr.min_pass_rate:
        trips.append(Trip("pass_rate", f"pass rate {pr:.1%} over {decided} reviewed candidates is under {sr.min_pass_rate:.0%}"))
    if keymod.statuses(con, "apify"):         # only judge credit once balances have been checked
        credit = keymod.usable_credit(con, floor if floor is not None else cfg.budget.min_key_balance_usd)
        if credit < sr.min_usable_credit:
            trips.append(Trip("usable_credit", f"usable Apify credit is ${credit:.2f}, under ${sr.min_usable_credit:.2f}"))
    last = con.execute("SELECT id FROM cycles WHERE pipeline=? AND id<? AND status='ended' ORDER BY id DESC LIMIT ?", (cfg.name, cycle_id, sr.low_yield_cycles)).fetchall()
    if len(last) == sr.low_yield_cycles and all(rows_appended(con, r[0]) < sr.low_yield_rows for r in last):
        trips.append(Trip("low_yield", f"the last {sr.low_yield_cycles} cycles each added fewer than {sr.low_yield_rows} rows"))
    return trips


def sync_stop_events(con, cfg: PipelineConfig, cycle_id: int) -> list[sqlite3.Row]:
    """Record newly tripped rules (once per rule per cycle) and return the unacknowledged ones. Paid steps stay blocked while any exist."""
    for t in evaluate_stop_rules(con, cfg, cycle_id):
        con.execute("INSERT OR IGNORE INTO stop_events (cycle_id, rule, reason) VALUES (?,?,?)", (cycle_id, t.rule, t.reason))
    return open_stop_events(con, cycle_id)


def open_stop_events(con, cycle_id: int) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM stop_events WHERE cycle_id=? AND acknowledged_at IS NULL ORDER BY id", (cycle_id,)).fetchall()


def acknowledge(con, event_id: int) -> None:
    con.execute("UPDATE stop_events SET acknowledged_at=CURRENT_TIMESTAMP WHERE id=?", (event_id,))
