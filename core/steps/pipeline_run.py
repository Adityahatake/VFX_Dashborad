"""The one-click VFX pipeline (`vfx_pipeline`): every stage in order, inside ONE worker job, with live progress for the dashboard.

  1 Initializing pipeline        run record, checkpoint
  2 Checking API keys            free balance checks; needs a usable Tavily key
  3 Searching for VFX companies  harvest_tavily_press (Tavily credits)                      SOP 01 s5: candidates only
  4 Processing company results   deep_crawl of each candidate's own site, then qualify.py    SOP 01 machine checks
  5 Searching for people         leads_finder on qualified companies (Apify), pool_match (free)
  6 Processing and validating    every new person checked against the sheet (read-only): duplicates, 3-per-company, countries
  7 Saving data                  counts and the run record; valid people wait in the database for review
  8 Pipeline completed

Safety, unchanged from the single steps:
  - the user confirms ONE maximum cost at the gate; every paid stage is sized to what is left of it and of the cycle cap, and the
    stop rules are re-checked before each paid stage (a trip skips the remaining paid stages, it never lowers the quality bar);
  - keys come from the pool one at a time under a lease (one job per key), and a key that runs out is marked and swapped;
  - pilot rule: a source never paid for here runs at pilot size (25) first;
  - nothing is written to the sheet. Approved rows still go through Review and the confirmed append.
Resumable: finished stages are checkpointed; the sub-steps are themselves resumable or cached (same tag on resume)."""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .. import dedupe, fields as F, jobs, keys, qualify, spend
from .base import CostEstimate, Step, StepContext, StepResult, get_step, register
from .crawl import CrawlParams
from .discover import TAVILY_SOURCE, TavilyParams
from .harvest import _need_pipeline
from .paid import LEADS_ACTOR, LeadsParams
from .people_free import PoolMatchParams

STAGES = ["Initializing pipeline", "Checking API keys", "Searching for VFX companies using Tavily", "Processing company results",
          "Searching for people", "Processing and validating records", "Saving data to the database", "Pipeline completed"]
WEIGHTS = [2, 3, 20, 35, 20, 10, 5, 5]               # share of the progress bar per stage
PILOT = 25


class NoKey(Exception):
    pass


class RunParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tavily_queries: int = Field(20, ge=1, le=200)
    tavily_max_results: int = Field(10, ge=1, le=20)
    time_range: Literal["day", "week", "month", "year"] | None = "month"
    crawl_limit: int = Field(60, ge=1, le=5000)
    crawl_threads: int = Field(24, ge=1, le=64)
    min_evidence_score: int = Field(2, ge=1, le=20)  # crawl sentences needed for an automatic PASS; fewer -> held for a look
    leads_max_result: int = Field(50, ge=1, le=500)
    pool_match: bool = True
    tavily_price_per_credit: float = Field(0.008, gt=0)
    leads_price_per_result: float = Field(0.003, gt=0)


class Progress:
    """progress.json next to the job log (the dashboard polls it) plus the pipeline_runs row (history and analytics)."""

    def __init__(self, ctx: StepContext, budget: float):
        self.ctx, self.path = ctx, ctx.job_dir / "progress.json"
        old = {}
        try:
            old = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        self.d = {"stages": STAGES, "stage_index": 0, "stage": STAGES[0], "step": "", "percent": 0.0, "budget_usd": budget,
                  "counts": {}, "api": {}, "errors": [], "warnings": [], **old}
        self._frac = 0.0

    def stage(self, i: int, step: str = "") -> None:
        self.d.update(stage_index=i, stage=STAGES[i], step=step)
        self._frac = 0.0
        self.ctx.log(f"== {i + 1}/{len(STAGES)} {STAGES[i]}" + (f" ({step})" if step else ""))
        self.save()

    def step(self, name: str) -> None:
        self.d["step"] = name
        self.save()

    def frac(self, f: float) -> None:
        self._frac = max(0.0, min(1.0, f))
        self.save()

    def count(self, **kw) -> None:
        self.d["counts"].update(kw)
        self.save()

    def error(self, msg: str) -> None:
        self.d["errors"].append(msg)
        self.ctx.log("ERROR: " + msg)
        self.save()

    def warn(self, msg: str) -> None:
        self.d["warnings"].append(msg)
        self.ctx.log("WARNING: " + msg)
        self.save()

    def save(self) -> None:
        i = self.d["stage_index"]
        done = sum(WEIGHTS[:i]) + WEIGHTS[i] * (1.0 if i == len(STAGES) - 1 else self._frac)
        self.d["percent"] = round(100.0 * done / sum(WEIGHTS), 1)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        db = self.ctx.db
        db.execute("UPDATE pipeline_runs SET stage=?, counts_json=?, errors_json=?, spent_usd=? WHERE job_id=?",
                   (self.d["stage"], json.dumps({**self.d["counts"], **{"api_" + k: v for k, v in self.d["api"].items()}}),
                    json.dumps(self.d["errors"]), self.d["api"].get("total_usd", 0.0), self.ctx.job_id))

    def from_log(self, m: str) -> None:
        """Turn the sub-steps' progress lines into a fraction of the current stage."""
        x = re.search(r"search (\d+)/(\d+)", m) or re.search(r"(\d+)/(\d+) crawled", m)
        if x and int(x.group(2)):
            self.frac(int(x.group(1)) / int(x.group(2)))


def read_progress(job_id: int) -> dict | None:
    try:
        return json.loads((jobs.job_dir(job_id) / "progress.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@register
class VfxPipeline(Step):
    id = "vfx_pipeline"
    kind = "paid"
    title = "Run the full VFX pipeline (Tavily -> crawl -> checks -> people -> validation)"
    params_model = RunParams

    def estimate_cost(self, ctx, p: RunParams) -> CostEstimate:
        t, l = p.tavily_queries * p.tavily_price_per_credit, p.leads_max_result * p.leads_price_per_result
        return CostEstimate(max_usd=round(t + l, 6), provider="", key_required=False,
                            note=f"Tavily {p.tavily_queries} searches (${t:.3f}) + leads up to {p.leads_max_result} (${l:.3f}); keys picked from the pool per stage")

    def resume(self, ctx: StepContext, p: RunParams) -> StepResult:
        return self.run(ctx, p)

    # ------------------------------------------------------------------ helpers
    def _sub(self, ctx: StepContext, prog: Progress) -> StepContext:
        """A context for one sub-step: same job, logs feed the progress bar, keys come from the pool under a lease."""
        con, demo, floor = ctx.db, keys.is_demo(ctx.db), ctx.cfg.budget.min_key_balance_usd

        @contextmanager
        def use_key(provider: str):
            k = keys.pick_key(con, provider, floor if provider == "apify" else 0.0)
            if k is None:
                raise NoKey(f"no usable {keys.LABELS.get(provider, provider)} key with a fresh check (add or top up keys on API & Keys)")
            ctx.log(f"using {provider} key {k.key_id}")
            with jobs.lease(con, k.key_id, ctx.job_id):
                yield k.key_id, keys.secret_for(provider, k.key_id, demo)

        def log(m: str) -> None:
            ctx.log("   " + m)
            prog.from_log(m)

        return StepContext(job_id=ctx.job_id, cycle_id=ctx.cycle_id, workdir=ctx.workdir, job_dir=ctx.job_dir, log=log,
                           is_cancelled=ctx._is_cancelled, lease=ctx._lease, use_key=use_key, record_spend=ctx._record_spend,
                           cfg=ctx.cfg, db=con, pipeline_dir=ctx.pipeline_dir, sheet=ctx._sheet, sheet_factory=ctx._sheet_factory)

    def _spent(self, con, cid: int, ledger_start: int) -> dict:
        r = {k: 0.0 for k in ("tavily_usd", "apify_usd")}
        for row in con.execute("SELECT kind, SUM(actual_usd) s, SUM(results) n FROM spend_ledger WHERE id>? AND cycle_id=? GROUP BY kind", (ledger_start, cid)):
            r[f"{row['kind']}_usd"] = round(row["s"] or 0, 4)
        r["total_usd"] = round(sum(r.values()), 4)
        return r

    def _paid_ok(self, ctx: StepContext, prog: Progress, need_usd: float, budget: float, ledger_start: int) -> float:
        """How much this paid stage may spend (0 = skip it): what is left of the run budget and the cycle cap, after the stop rules."""
        trips = spend.evaluate_stop_rules(ctx.db, ctx.cfg, ctx.cycle_id)
        if trips:
            prog.warn("stop rule tripped, paid stages skipped: " + "; ".join(f"{t.rule}: {t.reason}" for t in trips))
            return 0.0
        left = budget - self._spent(ctx.db, ctx.cycle_id, ledger_start)["total_usd"]
        cyc = ctx.db.execute("SELECT cap_usd FROM cycles WHERE id=?", (ctx.cycle_id,)).fetchone()["cap_usd"]
        left = min(left, cyc - spend.cycle_spend(ctx.db, ctx.cycle_id))
        return max(0.0, round(min(left, need_usd), 6))

    # ------------------------------------------------------------------ the run
    def run(self, ctx: StepContext, p: RunParams) -> StepResult:
        _need_pipeline(ctx)
        con, cfg, cid, jid = ctx.db, ctx.cfg, ctx.cycle_id, ctx.job_id
        if cid is None:
            raise ValueError("start a cycle first (goal and spend cap), then run the pipeline")
        job = con.execute("SELECT est_max_usd FROM jobs WHERE id=?", (jid,)).fetchone()
        budget = float(job["est_max_usd"]) if job and job["est_max_usd"] else self.estimate_cost(None, p).max_usd
        con.execute("INSERT OR IGNORE INTO pipeline_runs (job_id, cycle_id, budget_usd) VALUES (?,?,?)", (jid, cid, budget))
        con.execute("UPDATE pipeline_runs SET status='running', finished_at=NULL WHERE job_id=?", (jid,))
        ck = ctx.load_checkpoint()
        if "ledger_start" not in ck:
            ck = {"stage": 0, "ledger_start": con.execute("SELECT COALESCE(MAX(id),0) FROM spend_ledger").fetchone()[0],
                  "people_start": con.execute("SELECT COALESCE(MAX(id),0) FROM people").fetchone()[0]}
        prog, tag = Progress(ctx, budget), f"r{jid}"
        sub = self._sub(ctx, prog)

        def done_stage(i: int) -> None:
            ck["stage"] = i + 1
            ctx.save_checkpoint(ck)
            prog.d["api"] = self._spent(con, cid, ck["ledger_start"])
            prog.save()

        try:
            # 1 ----------------------------------------------------------------
            if ck["stage"] <= 0:
                prog.stage(0)
                ctx.log(f"cycle {cid}, run budget ${budget:.3f}, tag {tag}")
                done_stage(0)

            # 2 ----------------------------------------------------------------
            if ck["stage"] <= 1:
                prog.stage(1, "balance checks (free)")
                keys.check_all(con)
                ok = {pr: keys.pick_key(con, pr, cfg.budget.min_key_balance_usd if pr == "apify" else 0.0) is not None for pr in ("tavily", "apify")}
                prog.count(tavily_key_ready=ok["tavily"], apify_key_ready=ok["apify"])
                if not ok["tavily"]:
                    raise NoKey("no usable Tavily key: add one on API & Keys (company discovery needs it)")
                if not ok["apify"]:
                    prog.warn("no usable Apify key: the paid people search will be skipped (free pool matching still runs)")
                try:
                    prog.step("reading the sheet (read-only snapshot)")
                    get_step("sheet_snapshot").run(sub, get_step("sheet_snapshot").params_model())
                    ck["snapshot"] = True
                except Exception as e:                                       # no credentials / no network: later checks say what they skipped
                    ck["snapshot"] = False
                    prog.warn(f"sheet snapshot failed ({type(e).__name__}: {e}); pool matching and duplicate checks are skipped")
                done_stage(1)

            # 3 ----------------------------------------------------------------
            if ck["stage"] <= 2:
                prog.stage(2, "harvest_tavily_press")
                tv = TavilyParams(tag=tag, max_queries=p.tavily_queries, max_results=p.tavily_max_results, time_range=p.time_range,
                                  price_per_credit=p.tavily_price_per_credit)
                if not spend.has_run(con, TAVILY_SOURCE) and tv.max_queries > PILOT:
                    prog.warn(f"pilot rule: Tavily has never been paid for here, so this run makes at most {PILOT} searches")
                    tv.max_queries = PILOT
                allowed = self._paid_ok(ctx, prog, tv.max_queries * tv.price_per_credit, budget, ck["ledger_start"])
                tv.max_queries = int(allowed // tv.price_per_credit + 1e-9)
                if tv.max_queries < 1:
                    prog.warn("no budget left for the Tavily search")
                else:
                    step = get_step("harvest_tavily_press")
                    for attempt in range(3):                                 # a key that runs out mid-way is marked; the next one continues
                        r = step.run(sub, tv)
                        if r.status == "done":
                            break
                        keys.check_all(con)
                    prog.count(tavily_searches=r.counts.get("searches", 0), tavily_failed=r.counts.get("failed", 0), companies_found=r.counts.get("candidates", 0))
                    if r.counts.get("failed"):
                        prog.warn(f"{r.counts['failed']} Tavily searches failed and were skipped")
                done_stage(2)

            # 4 ----------------------------------------------------------------
            if ck["stage"] <= 3:
                prog.stage(3, "deep_crawl")
                dom = ctx.workdir / f"{tag}_domains.json"
                if dom.exists() and json.loads(dom.read_text(encoding="utf-8")):
                    r = get_step("deep_crawl").run(sub, CrawlParams(tag=tag, source="domains", threads=p.crawl_threads, limit=p.crawl_limit))
                    prog.count(companies_crawled=r.counts.get("crawled", 0), companies_with_evidence=r.counts.get("with_evidence", 0),
                               companies_unreachable=r.counts.get("unreachable", 0))
                else:
                    prog.warn("no new candidate companies to crawl")
                prog.step("qualification checks (SOP 01)")
                q = qualify.qualify_cycle(con, cfg, cid, p.min_evidence_score, source_prefix=tag + ":")
                prog.count(companies_qualified=q["approved"], companies_held=q["look"], companies_rejected=q["rejected"])
                done_stage(3)

            # 5 ----------------------------------------------------------------
            if ck["stage"] <= 4:
                prog.stage(4, "leads_finder")
                have = {r[0] for r in con.execute("SELECT DISTINCT domain FROM people WHERE cycle_id=?", (cid,))}
                todo = [r[0] for r in con.execute("SELECT domain FROM companies WHERE cycle_id=? AND decision='approved'", (cid,)) if r[0] not in have]
                prog.count(companies_for_people=len(todo))
                if not todo:
                    prog.warn("no qualified companies without people yet: the paid people search is skipped")
                else:
                    keys.check_all(con)                                      # free; the crawl may have taken longer than a balance check stays fresh
                    lp = LeadsParams(tag=tag, max_result=p.leads_max_result, price_per_result=p.leads_price_per_result)
                    if not spend.has_run(con, LEADS_ACTOR) and lp.max_result > PILOT:
                        prog.warn(f"pilot rule: leads finder has never been paid for here, so at most {PILOT} results")
                        lp.max_result = PILOT
                    allowed = self._paid_ok(ctx, prog, lp.max_result * lp.price_per_result, budget, ck["ledger_start"])
                    lp.max_result = int(allowed // lp.price_per_result + 1e-9)
                    if lp.max_result < 1:
                        prog.warn("no budget left for the people search")
                    else:
                        try:
                            r = get_step("leads_finder").run(sub, lp)
                            prog.count(leads=r.counts.get("leads", 0), people_found=r.counts.get("candidates", 0))
                        except NoKey as e:
                            prog.error(str(e))
                if p.pool_match and ck.get("snapshot"):
                    prog.step("pool_match (free)")
                    try:
                        r = get_step("pool_match").run(sub, PoolMatchParams(tag=tag))
                        prog.count(pool_matches=r.counts.get("candidates", r.counts.get("added", 0)))
                    except Exception as e:
                        prog.warn(f"pool matching skipped ({type(e).__name__}: {e})")
                done_stage(4)

            # 6 ----------------------------------------------------------------
            if ck["stage"] <= 5:
                prog.stage(5, "checks against the sheet (read-only)")
                new = con.execute("SELECT * FROM people WHERE cycle_id=? AND id>? AND decision='pending' ORDER BY id", (cid, ck["people_start"])).fetchall()
                valid = held = rejected = 0
                st = None
                try:
                    st, _ = dedupe.read_state(sub.sheet, cfg)
                except Exception as e:
                    prog.warn(f"sheet not readable ({type(e).__name__}); duplicate checks are left to the append dry run")
                cols = cfg.output.columns
                for i, r in enumerate(new):
                    ctx.check_cancel()
                    row = F.row_from_fields(cfg, json.loads(r["fields_json"]))
                    if st is None:
                        valid += 1
                        continue
                    ok, rej = dedupe.check_rows([row], cfg, st)
                    if ok:
                        st.add(cols, ok[0], cfg)
                        valid += 1
                    else:
                        why = rej[0][2]
                        dec = "look" if "empty" in why else "rejected"
                        con.execute("UPDATE people SET decision=?, reason_code=?, decided_at=CURRENT_TIMESTAMP WHERE id=? AND decision='pending'",
                                    (dec, ("AUTO_HOLD:" if dec == "look" else "AUTO_REJECT:") + why, r["id"]))
                        held += dec == "look"
                        rejected += dec == "rejected"
                    prog.frac((i + 1) / max(1, len(new)))
                prog.count(people_checked=len(new), people_valid=valid, people_held=held, people_rejected=rejected)
                done_stage(5)

            # 7 ----------------------------------------------------------------
            if ck["stage"] <= 6:
                prog.stage(6, "run record")
                c = prog.d["counts"]
                prog.count(records_saved=c.get("people_valid", 0) + c.get("companies_qualified", 0),
                           records_skipped=c.get("people_rejected", 0) + c.get("companies_rejected", 0),
                           records_held=c.get("people_held", 0) + c.get("companies_held", 0))
                done_stage(6)

            prog.stage(7)
            prog.d["api"] = self._spent(con, cid, ck["ledger_start"])
            prog.save()
            con.execute("UPDATE pipeline_runs SET status='done', finished_at=CURRENT_TIMESTAMP WHERE job_id=?", (jid,))
        except BaseException as e:
            status = "cancelled" if type(e).__name__ == "Cancelled" else "failed"
            if status == "failed":
                prog.error(f"{type(e).__name__}: {e}")
            con.execute("UPDATE pipeline_runs SET status=?, finished_at=CURRENT_TIMESTAMP WHERE job_id=?", (status, jid))
            raise
        c = prog.d["counts"]
        msg = (f"{c.get('companies_found', 0)} companies found, {c.get('companies_qualified', 0)} qualified, "
               f"{c.get('people_valid', 0)} people saved for review, ${prog.d['api'].get('total_usd', 0):.3f} spent")
        return StepResult(counts={k: v for k, v in c.items() if isinstance(v, int) and not isinstance(v, bool)}, message=msg,
                          actual_cost=prog.d["api"].get("total_usd", 0.0))
