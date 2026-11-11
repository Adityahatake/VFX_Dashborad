"""Read-only statistics for the Analytics page, computed from the stored data only (no sample values).

Time columns: companies.created_at / people.created_at (rows from before migration 7 carry their cycle's start time), spend_ledger.ts,
appended_rows.ts, pipeline_runs.started_at / finished_at, jobs.started_at. All are UTC."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

BUCKETS = {"day": "date({c})", "week": "strftime('%Y-W%W', {c})", "month": "strftime('%Y-%m', {c})"}


def _range(col: str, frm: str | None, to: str | None) -> tuple[str, list]:
    """WHERE fragment for an inclusive date range on a timestamp column (`to` includes the whole day)."""
    w, a = [], []
    if frm:
        w.append(f"{col} >= ?")
        a.append(frm)
    if to:
        w.append(f"{col} < date(?, '+1 day')")
        a.append(to)
    return (" AND ".join(w) or "1=1"), a


def _series(con, table: str, col: str, b: str, frm, to, extra: dict[str, str]) -> list[dict]:
    """[{bucket, n, <extra name>: count where <condition>}] per time bucket."""
    w, a = _range(col, frm, to)
    cols = ", ".join(f"SUM(CASE WHEN {cond} THEN 1 ELSE 0 END) AS {name}" for name, cond in extra.items())
    q = f"SELECT {BUCKETS[b].format(c=col)} AS bucket, COUNT(*) AS n{', ' + cols if cols else ''} FROM {table} WHERE {col} IS NOT NULL AND {w} GROUP BY bucket ORDER BY bucket"
    return [dict(r) for r in con.execute(q, a)]


def _count(con, q: str, a: list) -> int:
    return con.execute(q, a).fetchone()[0] or 0


def summary(con: sqlite3.Connection, frm: str | None = None, to: str | None = None, bucket: str = "day") -> dict:
    if bucket not in BUCKETS:
        raise ValueError(f"bucket must be one of {list(BUCKETS)}")
    wc, ac = _range("created_at", frm, to)
    wr, ar = _range("r.started_at", frm, to)
    ws, as_ = _range("ts", frm, to)

    companies = _count(con, f"SELECT COUNT(*) FROM companies WHERE {wc}", ac)
    qualified = _count(con, f"SELECT COUNT(*) FROM companies WHERE decision='approved' AND {wc}", ac)
    people = _count(con, f"SELECT COUNT(*) FROM people WHERE {wc}", ac)
    people_ok = _count(con, f"SELECT COUNT(*) FROM people WHERE decision='approved' AND {wc}", ac)
    appended = _count(con, f"SELECT COUNT(*) FROM appended_rows WHERE {ws}", as_)

    runs = [dict(r) for r in con.execute(
        f"SELECT r.*, (julianday(r.finished_at) - julianday(r.started_at)) * 1440 AS minutes FROM pipeline_runs r WHERE {wr} ORDER BY r.job_id", ar)]
    for r in runs:
        r["counts"] = json.loads(r.pop("counts_json") or "{}")
        r["errors"] = len(json.loads(r.pop("errors_json") or "[]"))
    finished = [r["minutes"] for r in runs if r["minutes"] is not None and r["status"] == "done"]
    by_status: dict[str, int] = {}
    for r in runs:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    spend_kind = {r["kind"]: {"usd": round(r["usd"] or 0, 4), "calls": r["n"], "results": r["res"] or 0}
                  for r in con.execute(f"SELECT kind, SUM(actual_usd) usd, COUNT(*) n, SUM(results) res FROM spend_ledger WHERE {ws} GROUP BY kind", as_)}
    spend_series: dict[str, dict] = {}
    for r in con.execute(f"SELECT {BUCKETS[bucket].format(c='ts')} AS bucket, kind, SUM(actual_usd) usd FROM spend_ledger WHERE {ws} GROUP BY bucket, kind ORDER BY bucket", as_):
        spend_series.setdefault(r["bucket"], {"bucket": r["bucket"]})[r["kind"]] = round(r["usd"] or 0, 4)

    run_series: dict[str, dict] = {}
    for r in runs:
        b = con.execute(f"SELECT {BUCKETS[bucket].format(c='?')}", (r["started_at"],)).fetchone()[0]
        s = run_series.setdefault(b, {"bucket": b, "done": 0, "failed": 0, "other": 0})
        s[r["status"] if r["status"] in ("done", "failed") else "other"] += 1

    today = date.today()
    windows = {"today": today, "last_7_days": today - timedelta(days=6), "last_30_days": today - timedelta(days=29)}
    collection = {k: {"companies": _count(con, "SELECT COUNT(*) FROM companies WHERE created_at >= ?", [d.isoformat()]),
                      "people": _count(con, "SELECT COUNT(*) FROM people WHERE created_at >= ?", [d.isoformat()])} for k, d in windows.items()}

    steps = [dict(r) for r in con.execute(
        f"SELECT step_id, COUNT(*) n, SUM(status='done') done, SUM(status='failed') failed FROM jobs WHERE {_range('started_at', frm, to)[0]} GROUP BY step_id ORDER BY n DESC",
        _range("started_at", frm, to)[1])]

    return {
        "range": {"from": frm, "to": to, "bucket": bucket},
        "totals": {
            "companies": companies, "companies_qualified": qualified, "people": people, "people_approved": people_ok, "rows_appended": appended,
            "runs": len(runs), "runs_by_status": by_status,
            "avg_run_minutes": round(sum(finished) / len(finished), 2) if finished else None,
            "people_per_qualified_company": round(people / qualified, 2) if qualified else None,
            "spend_usd": round(sum(v["usd"] for v in spend_kind.values()), 4),
        },
        "collection": collection,
        "series": {
            "companies": _series(con, "companies", "created_at", bucket, frm, to, {"approved": "decision='approved'", "rejected": "decision='rejected'"}),
            "people": _series(con, "people", "created_at", bucket, frm, to, {"approved": "decision='approved'", "rejected": "decision='rejected'"}),
            "spend": list(spend_series.values()),
            "runs": sorted(run_series.values(), key=lambda x: x["bucket"]),
        },
        "spend_by_kind": spend_kind,
        "runs": [{"job_id": r["job_id"], "status": r["status"], "started_at": r["started_at"], "minutes": round(r["minutes"], 2) if r["minutes"] is not None else None,
                  "spent_usd": r["spent_usd"], "companies_found": r["counts"].get("companies_found", 0), "companies_qualified": r["counts"].get("companies_qualified", 0),
                  "people_found": r["counts"].get("people_found", 0), "people_valid": r["counts"].get("people_valid", 0),
                  "records_saved": r["counts"].get("records_saved", 0), "records_skipped": r["counts"].get("records_skipped", 0), "errors": r["errors"]} for r in runs],
        "steps": steps,
    }
