"""History and metrics: per-cycle results, source yield (screened -> hits -> verified -> rows), paid-step cost, LLM-vs-reviewer agreement, and
warnings about sources already known to be exhausted. All read-only queries over the same tables the rest of the app writes."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from . import spend
from .config import ExhaustedSource, PipelineConfig
from .review import PERSON_REASONS, REJECT_REASONS

DEAD_SOURCE_MIN_SCREENED = 200        # a source with this many sites screened and nothing verified is a candidate for the exhausted list


def _hours(a: str | None, b: str | None) -> float | None:
    if not a:
        return None
    t0 = datetime.strptime(a, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    t1 = datetime.strptime(b, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) if b else datetime.now(timezone.utc)
    return round((t1 - t0).total_seconds() / 3600, 2)


def cycles_overview(con: sqlite3.Connection, pipeline: str | None = None) -> list[dict]:
    q, a = "SELECT * FROM cycles" + (" WHERE pipeline=?" if pipeline else "") + " ORDER BY id DESC", ((pipeline,) if pipeline else ())
    out = []
    for c in con.execute(q, a).fetchall():
        cid = c["id"]
        conf = {r[0] or "": r[1] for r in con.execute(
            "SELECT json_extract(p.fields_json,'$.qa_confidence'), COUNT(*) FROM appended_rows ar JOIN people p ON p.cycle_id=ar.cycle_id "
            "AND json_extract(p.fields_json,'$.contact_or_reference')=ar.url WHERE ar.cycle_id=? GROUP BY 1", (cid,))}
        rej_c = {REJECT_REASONS.get(r[0], r[0] or "unspecified"): r[1] for r in con.execute(
            "SELECT reason_code, COUNT(*) FROM companies WHERE cycle_id=? AND decision='rejected' GROUP BY 1", (cid,))}
        rej_p = {PERSON_REASONS.get(r[0], r[0] or "unspecified"): r[1] for r in con.execute(
            "SELECT reason_code, COUNT(*) FROM people WHERE cycle_id=? AND decision='rejected' GROUP BY 1", (cid,))}
        rows = spend.rows_appended(con, cid)
        pr, decided = spend.pass_rate(con, cid)
        out.append({
            "cycle": cid, "pipeline": c["pipeline"], "status": c["status"], "goal": c["goal_rows"], "rows": rows,
            "high": conf.get("High", 0), "medium": conf.get("Medium", 0), "other": rows - conf.get("High", 0) - conf.get("Medium", 0),
            "spend_usd": spend.cycle_spend(con, cid), "llm_usd": spend.llm_spend(con, cid), "cap_usd": c["cap_usd"],
            "cost_per_row": (round(spend.cycle_spend(con, cid) / rows, 3) if rows else None), "pass_rate": pr, "reviewed": decided,
            "hours": _hours(c["started_at"], c["ended_at"]), "started": c["started_at"],
            "company_rejections": rej_c, "person_rejections": rej_p,
            "spend_by_source": [{"source": r["source"], "kind": r["kind"], "usd": round(r["usd"] or 0, 4), "calls": r["calls"], "results": r["results"] or 0} for r in spend.by_source(con, cid)],
        })
    return out


def source_yield(con: sqlite3.Connection, pipeline: str) -> list[dict]:
    """One row per discovery source (tag:category): screened -> crawl hits -> approved in review -> rows on the sheet. Free sources cost $0."""
    screened = {r["source"]: (r["s"], r["h"]) for r in con.execute(
        "SELECT source, SUM(screened) s, SUM(hits) h FROM source_yield WHERE pipeline=? GROUP BY source", (pipeline,))}
    sources = set(screened) | {r[0] for r in con.execute("SELECT DISTINCT c.source FROM companies c JOIN cycles y ON y.id=c.cycle_id WHERE y.pipeline=? AND c.source IS NOT NULL", (pipeline,))}
    out = []
    for s in sorted(sources):
        hits_db = con.execute("SELECT COUNT(*) FROM companies c JOIN cycles y ON y.id=c.cycle_id WHERE y.pipeline=? AND c.source=?", (pipeline, s)).fetchone()[0]
        verified = con.execute("SELECT COUNT(*) FROM companies c JOIN cycles y ON y.id=c.cycle_id WHERE y.pipeline=? AND c.source=? AND c.decision='approved'", (pipeline, s)).fetchone()[0]
        rows = con.execute(
            "SELECT COUNT(DISTINCT ar.id) FROM appended_rows ar JOIN people p ON p.cycle_id=ar.cycle_id AND json_extract(p.fields_json,'$.contact_or_reference')=ar.url "
            "JOIN companies c ON c.cycle_id=p.cycle_id AND c.domain=p.domain JOIN cycles y ON y.id=ar.cycle_id WHERE y.pipeline=? AND c.source=?", (pipeline, s)).fetchone()[0]
        scr, h = screened.get(s, (0, hits_db))
        out.append({"source": s, "screened": scr, "hits": max(h, hits_db), "verified": verified, "rows": rows, "cost_usd": 0.0,
                    "hit_rate": (round(h / scr, 4) if scr else None), "dead": bool(scr >= DEAD_SOURCE_MIN_SCREENED and verified == 0)})
    return sorted(out, key=lambda r: (-r["rows"], -r["verified"], -r["hits"], r["source"]))


def paid_steps(con: sqlite3.Connection, pipeline: str) -> list[dict]:
    """Paid and LLM spend by actor/model across the pipeline's cycles (imported VFX history has no cycle and is shown separately)."""
    rows = con.execute(
        "SELECT l.source, l.kind, COUNT(*) calls, SUM(l.actual_usd) usd, SUM(l.results) results FROM spend_ledger l JOIN cycles y ON y.id=l.cycle_id "
        "WHERE y.pipeline=? GROUP BY l.source, l.kind ORDER BY usd DESC", (pipeline,)).fetchall()
    hist = con.execute("SELECT source, COUNT(*) calls, SUM(actual_usd) usd, SUM(results) results FROM spend_ledger WHERE cycle_id IS NULL AND note LIKE 'imported:%' GROUP BY source ORDER BY usd DESC").fetchall()
    return ([{"source": r["source"], "kind": r["kind"], "calls": r["calls"], "usd": round(r["usd"] or 0, 4), "results": r["results"] or 0, "origin": "this app"} for r in rows]
            + [{"source": r["source"], "kind": "apify", "calls": r["calls"], "usd": round(r["usd"] or 0, 4), "results": r["results"] or 0, "origin": "VFX history (imported)"} for r in hist])


def llm_agreement(con: sqlite3.Connection, pipeline: str) -> list[dict]:
    """How often the reviewer's decision matched the LLM's yes/no, per model and prompt version. 'unsure' answers are not counted either way.
    A rising or falling line over cycles is the signal to trust or distrust the suggestions; it is information, never a gate."""
    out: dict[tuple, dict] = {}
    for c in con.execute("SELECT c.cycle_id, c.decision, c.llm_json FROM companies c JOIN cycles y ON y.id=c.cycle_id WHERE y.pipeline=? AND c.llm_json IS NOT NULL AND c.decision IN ('approved','rejected')", (pipeline,)):
        v = json.loads(c["llm_json"])
        if v.get("qualifies") not in ("yes", "no") or v.get("error"):
            continue
        k = (v.get("model", "?"), v.get("prompt_version", "?"), c["cycle_id"])
        r = out.setdefault(k, {"model": k[0], "prompt": k[1], "cycle": k[2], "decided": 0, "agree": 0, "false_yes": 0})
        r["decided"] += 1
        agree = (v["qualifies"] == "yes") == (c["decision"] == "approved")
        r["agree"] += agree
        r["false_yes"] += (v["qualifies"] == "yes" and c["decision"] == "rejected")
    res = sorted(out.values(), key=lambda r: (r["model"], r["cycle"]))
    for r in res:
        r["agreement"] = round(r["agree"] / r["decided"], 3) if r["decided"] else None
    return res


def matching_exhausted(cfg: PipelineConfig, step_id: str, params: dict | None) -> list[ExhaustedSource]:
    """Exhausted-source notes whose keywords appear in the step id or its parameters (case-insensitive substring). Shown BEFORE a rerun."""
    hay = (step_id + " " + json.dumps(params or {}, sort_keys=True)).casefold()
    return [e for e in cfg.exhausted_sources if any(m.casefold() in hay for m in e.match if m.strip())]
