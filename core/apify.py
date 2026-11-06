"""Apify runs, with the VFX rules built in (CLAUDE.md, "Spending"):
  * The run id is persisted (apify_runs) the moment it is known, BEFORE any waiting.
  * A network error NEVER relaunches a run. If starting the run fails with an unknown outcome, the actor's recent runs on the SAME key are
    listed and matched by their INPUT; the matching run's dataset is downloaded. If nothing matches, the job fails and a rerun needs a fresh
    confirmation at the gate (new cost check), it is never automatic.
  * A resumed job re-attaches to its persisted run instead of starting another one.
  * A definitive HTTP rejection (400, 401, 403, 429, 432) means the run did not start: the key is marked (rotation rules) and the job fails.
  * Cost is recorded in the ledger right after the dataset is downloaded (actual usage if the run reports it, else results x price)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from . import http, keys as keymod

BASE = "https://api.apify.com/v2"
TERMINAL = ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT")
REJECTED_CODES = (400, 401, 402, 403, 404, 429, 432)       # the request was refused: no run was created


class ApifyRejected(Exception):
    """The request was refused before a run was created (bad input, bad key, limit reached). `code` is the HTTP status."""

    def __init__(self, code: int, message: str = ""):
        super().__init__(f"Apify refused the request (HTTP {code}) {message}".strip())
        self.code = code


class RunNotFound(Exception):
    """Network error while starting, and no matching run exists on this key. Nothing was relaunched."""


class WaitFailed(Exception):
    """The run exists (its id is saved) but waiting for it or downloading its data failed. Resume re-attaches; it never starts a second run."""


class ApifyClient(Protocol):
    def start(self, actor: str, inp: dict) -> dict: ...
    def get_run(self, run_id: str) -> dict: ...
    def items(self, dataset_id: str) -> list[dict]: ...
    def list_runs(self, actor: str, limit: int = 10) -> list[dict]: ...
    def get_input(self, kv_store_id: str) -> dict: ...


class RealApify:
    def __init__(self, token: str):
        self.token = token

    def start(self, actor: str, inp: dict) -> dict:
        """POST /acts/<actor>/runs: sent once (http.post_json never retries)."""
        return http.post_json(f"{BASE}/acts/{urllib.parse.quote(actor, safe='~')}/runs", inp, self.token, timeout=60)["data"]

    def get_run(self, run_id: str) -> dict:
        return http.get_json(f"{BASE}/actor-runs/{run_id}", self.token, timeout=60)["data"]

    def items(self, dataset_id: str) -> list[dict]:
        out, off = [], 0
        while True:
            chunk = http.get_json(f"{BASE}/datasets/{dataset_id}/items?clean=true&offset={off}&limit=1000", self.token, timeout=90)
            out += chunk
            if len(chunk) < 1000:
                return out
            off += 1000

    def list_runs(self, actor: str, limit: int = 10) -> list[dict]:
        return http.get_json(f"{BASE}/acts/{urllib.parse.quote(actor, safe='~')}/runs?desc=1&limit={limit}", self.token, timeout=60)["data"]["items"]

    def get_input(self, kv_store_id: str) -> dict:
        return http.get_json(f"{BASE}/key-value-stores/{kv_store_id}/records/INPUT", self.token, timeout=60)


def get_client(con: sqlite3.Connection, token: str) -> ApifyClient:
    """Demo mode never touches the network: a deterministic fake actor stands in."""
    if keymod.is_demo(con):
        from .apify_fake import FakeApify, demo_actor_factory
        return FakeApify(actors=demo_actor_factory(), shared=True)
    return RealApify(token)


# ------------------------------------------------------------------ the run flow
def input_hash(inp: dict) -> str:
    return hashlib.sha256(json.dumps(inp, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


def _is_unknown_outcome(e: Exception) -> bool:
    """Did the POST possibly reach Apify? Connection errors, timeouts and 5xx: yes. 4xx: no, it was refused."""
    if isinstance(e, urllib.error.HTTPError):          # checked first: HTTPError is also a URLError/OSError
        return e.code >= 500
    return isinstance(e, (urllib.error.URLError, ConnectionError, TimeoutError, OSError))


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def recover(client: ApifyClient, actor: str, inp: dict, since: datetime, log: Callable[[str], None]) -> dict:
    """Find the run our failed start created: the newest run on this key whose INPUT contains all our input fields, started after `since`."""
    for r in client.list_runs(actor, 10):
        started = _parse_ts(r.get("startedAt") or r.get("createdAt") or "")
        if started and started < since - timedelta(seconds=60):
            continue
        try:
            stored = client.get_input(r["defaultKeyValueStoreId"])
        except Exception:
            continue
        if all(stored.get(k) == v for k, v in inp.items()):
            log(f"recovered run {r['id']} from the actor's run list (matched by INPUT); NOT relaunching")
            return r
    raise RunNotFound("network error while starting the run, and no matching run was found on this key. Nothing was relaunched; "
                      "check the run list in the Apify console, then start again through the gate (a new cost confirmation)")


def run_actor(client: ApifyClient, con: sqlite3.Connection, *, job_id: int, actor: str, inp: dict, key_id: str, log: Callable[[str], None],
              check_cancel: Callable[[], None] = lambda: None, wait_s: float = 800, poll_s: float = 8, sleep: Callable[[float], None] = time.sleep) -> tuple[str, list[dict], dict, bool]:
    """Start (or re-attach to) one run, wait, download. Returns (status, items, run, recovered)."""
    h, recovered = input_hash(inp), False
    row = con.execute("SELECT * FROM apify_runs WHERE job_id=? AND input_hash=? AND COALESCE(status,'')!='CONSUMED' ORDER BY created_at DESC, rowid DESC LIMIT 1", (job_id, h)).fetchone()
    if row:                                                         # resume: re-attach to an unfinished run, never start a second one
        log(f"re-attaching to saved run {row['run_id']} (not starting a new one)")
        try:
            run = client.get_run(row["run_id"])
        except Exception as e:
            raise WaitFailed(f"could not read saved run {row['run_id']}: {type(e).__name__}") from e
    else:
        since = datetime.now(timezone.utc)
        try:
            run = client.start(actor, inp)
        except Exception as e:                                      # noqa: BLE001
            if isinstance(e, urllib.error.HTTPError) and e.code in REJECTED_CODES:
                keymod.mark_failed(con, key_id, "apify", e.code, getattr(e, "reason", "") or "")
                raise ApifyRejected(e.code) from e
            if not _is_unknown_outcome(e):
                raise
            log(f"network error while starting ({type(e).__name__}); looking for the run instead of relaunching")
            try:
                run, recovered = recover(client, actor, inp, since, log), True
            except RunNotFound:
                raise
            except Exception as e2:
                raise WaitFailed(f"could not list runs to recover ({type(e2).__name__}); not relaunched") from e2
        con.execute("INSERT OR REPLACE INTO apify_runs (run_id, actor, key_prefix, input_hash, dataset_id, job_id, status) VALUES (?,?,?,?,?,?,?)",
                    (run["id"], actor, key_id, h, run.get("defaultDatasetId"), job_id, run.get("status")))   # saved BEFORE waiting
        log(f"run {run['id']} started on {key_id}")
    t0 = time.time()
    while run.get("status") not in TERMINAL:
        check_cancel()
        if time.time() - t0 > wait_s:
            raise WaitFailed(f"run {run['id']} still {run.get('status')} after {int(wait_s)}s; it keeps running on Apify. Resume to re-attach")
        sleep(poll_s)
        try:
            run = client.get_run(run["id"])
        except Exception as e:                                      # polling already retried inside http.get_json
            raise WaitFailed(f"lost contact with run {run['id']} ({type(e).__name__}); resume to re-attach, it is NOT relaunched") from e
    try:
        items = client.items(run["defaultDatasetId"])
    except Exception as e:
        raise WaitFailed(f"run {run['id']} finished but its data could not be downloaded ({type(e).__name__}); resume to re-attach") from e
    con.execute("UPDATE apify_runs SET status=?, dataset_id=? WHERE run_id=?", (run["status"], run.get("defaultDatasetId"), run["id"]))
    return run["status"], items, run, recovered


def actual_cost(run: dict, results: int, price: float, extra: float = 0.0) -> float:
    """What the run really cost: Apify's reported usage if present, else results x unit price (+ any fixed fee such as a search charge)."""
    u = run.get("usageTotalUsd")
    return round(float(u), 6) if isinstance(u, (int, float)) and u > 0 else round(results * price + extra, 6)


def mark_consumed(con: sqlite3.Connection, run_id: str) -> None:
    """The step has saved this run's data. A later identical request (e.g. the next Sales Navigator poll) must start a NEW run, not re-read this one."""
    con.execute("UPDATE apify_runs SET status='CONSUMED' WHERE run_id=?", (run_id,))


def spend_once(ctx, run_id: str, *, source: str, est_max_usd: float, actual_usd: float, results: int, key_id: str, note: str) -> bool:
    """Record a run's cost exactly once, even if the job is resumed after a crash between recording and saving. Returns False if already recorded."""
    tag = f"run:{run_id}"
    if ctx.db.execute("SELECT 1 FROM spend_ledger WHERE note LIKE ? AND cycle_id IS ?", (tag + "%", ctx.cycle_id)).fetchone():
        return False
    ctx.record_spend(source=source, est_max_usd=est_max_usd, actual_usd=actual_usd, results=results, key_id=key_id, note=f"{tag} {note}".strip())
    return True
