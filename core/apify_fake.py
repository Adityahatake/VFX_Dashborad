"""An in-memory Apify for tests and demo mode. It can drop the connection at every point where the real network can, so the
no-relaunch / recovery rules can be proven without spending anything. Never used outside tests and demo mode."""
from __future__ import annotations

import hashlib
import json
import urllib.error
from datetime import datetime, timezone
from typing import Callable


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.apify.com", code, "fake", {}, None)


class FakeApify:
    """actors: {actor: handler(input) -> list of dataset items}. Failure switches (set before the call that should fail):
      fail_start       'before'  the POST never reaches Apify (no run exists)      | 'after'  the run IS created, then the connection drops
                       or an int HTTP status (e.g. 403, 432, 500)
      fail_get_run     number of get_run calls that raise ConnectionError
      fail_items       number of items() calls that raise ConnectionError
      fail_list_runs   True: list_runs raises
      polls_until_done get_run returns RUNNING this many times before SUCCEEDED
      usage_usd        value of run['usageTotalUsd'] (None = not reported)
    Counters: start_calls, runs (all runs ever created)."""

    def __init__(self, actors: dict[str, Callable[[dict], list]], shared: bool = False):
        self.actors = actors
        self.runs: list[dict] = []
        self.inputs: dict[str, dict] = {}
        self.data: dict[str, list] = {}
        self.start_calls = 0
        self.fail_start = None
        self.fail_get_run = 0
        self.fail_items = 0
        self.fail_list_runs = False
        self.polls_until_done = 0
        self.usage_usd = None
        self._polls: dict[str, int] = {}
        self.final_status = "SUCCEEDED"

    def _create(self, actor: str, inp: dict) -> dict:
        n = len(self.runs) + 1
        rid, ds, kv = f"run{n}", f"ds{n}", f"kv{n}"
        self.inputs[kv] = json.loads(json.dumps(inp))
        self.data[ds] = self.actors[actor](inp) if self.final_status != "FAILED" else []
        run = {"id": rid, "actId": actor, "status": "RUNNING" if self.polls_until_done else self.final_status, "defaultDatasetId": ds, "defaultKeyValueStoreId": kv,
               "startedAt": datetime.now(timezone.utc).isoformat(), "usageTotalUsd": self.usage_usd, "_actor": actor}
        self.runs.append(run)
        self._polls[rid] = 0
        return run

    def start(self, actor: str, inp: dict) -> dict:
        self.start_calls += 1
        f, self.fail_start = self.fail_start, None
        if f == "before":
            raise ConnectionError("connection reset before the request was sent")
        if isinstance(f, int):
            raise _http_error(f)
        run = self._create(actor, inp)
        if f == "after":
            raise ConnectionError("connection dropped after the run was created")
        return dict(run)

    def get_run(self, run_id: str) -> dict:
        if self.fail_get_run > 0:
            self.fail_get_run -= 1
            raise ConnectionError("poll failed")
        run = next(r for r in self.runs if r["id"] == run_id)
        self._polls[run_id] += 1
        if run["status"] == "RUNNING" and self._polls[run_id] >= self.polls_until_done:
            run["status"] = self.final_status
        return dict(run)

    def items(self, dataset_id: str) -> list[dict]:
        if self.fail_items > 0:
            self.fail_items -= 1
            raise ConnectionError("download failed")
        return list(self.data[dataset_id])

    def list_runs(self, actor: str, limit: int = 10) -> list[dict]:
        if self.fail_list_runs:
            raise ConnectionError("list failed")
        return [dict(r) for r in reversed(self.runs) if r["_actor"] == actor][:limit]

    def get_input(self, kv_store_id: str) -> dict:
        return dict(self.inputs[kv_store_id])


# ------------------------------------------------------------------ demo-mode actors (synthetic data, clearly fake)
FIRST = ["Alex", "Bea", "Chris", "Dana", "Eli", "Fay", "Gabe", "Hana"]
LAST = ["Demo", "Sample", "Mock", "Fixture"]
TITLES = ["Founder & CEO", "Creative Director", "Executive Producer", "Head of Production", "CTO", "Junior Designer", "Sales Manager"]


def _leads(inp: dict) -> list[dict]:
    out = []
    for d in inp.get("company_domains", []):
        h = int(hashlib.sha1(d.encode()).hexdigest(), 16)
        for k in range(3):
            first, last, title = FIRST[(h + k) % 8], LAST[(h >> 4) % 4], TITLES[(h + k * 2) % len(TITLES)]
            out.append({"first_name": first, "last_name": f"{last}{k}", "title": title, "organization_primary_domain": d, "organization_name": d.split(".")[0].title(),
                        "linkedin_url": f"https://www.linkedin.com/in/{first.lower()}-{last.lower()}-{d.split('.')[0]}-{k}", "headline": f"{title} at {d.split('.')[0].title()}",
                        "city": "Berlin", "country": "Germany"})
    return out[: inp.get("max_result", 50)]


def demo_actor_factory() -> dict[str, Callable[[dict], list]]:
    return {"microworlds~leads-finder": _leads}
