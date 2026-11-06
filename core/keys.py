"""API keys: loaded from .env, shown by short id only, live balances (read-only calls), rotation, safe .env editing.
Demo mode (Settings toggle) swaps in three fake Apify keys and fake balances so the paid-step flow can be shown with zero network calls."""
from __future__ import annotations

import os
import shutil
import sqlite3
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import http, paths
from .db import get_setting

PROVIDERS = {"apify": ("apify_api_", "APIFY_TOKEN_POOL", 4), "tavily": ("tvly-", "TAVILY_API_KEYS", 8)}
APIFY_FLOOR = 0.80
STALE_S = 600
DEMO_KEYS = {"apify_api_AAAA_demo_not_a_real_key": (4.20, 5.0), "apify_api_BBBB_demo_not_a_real_key": (0.50, 5.0), "apify_api_CCCC_demo_not_a_real_key": None}


@dataclass
class KeyStatus:
    key_id: str
    provider: str
    state: str                  # usable | low | out | dead | error | unchecked
    remaining: float | None = None
    cap: float | None = None
    resets: str = ""
    checked_at: str = ""


def is_demo(con: sqlite3.Connection) -> bool:
    return get_setting(con, "demo_mode", "0") == "1"


def split_keys(v: str) -> list[str]:
    return list(dict.fromkeys(k.strip() for k in (v or "").replace(",", "\n").split() if k.strip()))


def key_id(key: str) -> str:
    """Display id: vendor prefix plus a few characters (never the whole key). e.g. apify_api_ZoxD."""
    for prefix, _, n in PROVIDERS.values():
        if key.startswith(prefix):
            return prefix + key[len(prefix):][:n]
    return key[:6] + "…"


def load_keys(provider: str, demo: bool = False) -> list[str]:
    if demo and provider == "apify":
        return list(DEMO_KEYS)
    if demo:
        return []
    return split_keys(os.environ.get(PROVIDERS[provider][1], ""))


def secret_for(provider: str, kid: str, demo: bool = False) -> str:
    for k in load_keys(provider, demo):
        if key_id(k) == kid:
            return k
    raise KeyError(f"no {provider} key with id {kid} in the environment")


# ------------------------------------------------------------------ live checks (read-only)
def check_apify(key: str, floor: float = APIFY_FLOOR, demo: bool = False) -> KeyStatus:
    kid = key_id(key)
    if demo:
        d = DEMO_KEYS[key]
        if d is None:
            return KeyStatus(kid, "apify", "dead", checked_at=_now())
        left, cap = d
        return KeyStatus(kid, "apify", "usable" if left >= floor else "low", left, cap, "2026-12-01", _now())
    try:
        d = http.get_json("https://api.apify.com/v2/users/me/limits", key)["data"]
        cap = d["limits"]["maxMonthlyUsageUsd"]
        left = max(0.0, round(cap - d["current"]["monthlyUsageUsd"], 2))
        resets = ((d.get("monthlyUsageCycle") or {}).get("endAt") or "")[:10]
    except urllib.error.HTTPError as e:
        return KeyStatus(kid, "apify", "dead" if e.code in (401, 403) else "error", checked_at=_now())
    except Exception:
        return KeyStatus(kid, "apify", "error", checked_at=_now())
    state = "usable" if left >= floor else ("low" if left > 0.005 else "out")
    return KeyStatus(kid, "apify", state, left, cap, resets, _now())


def check_tavily(key: str, live_search: bool = False) -> KeyStatus:
    """GET /usage is free. The account-wide plan limit only shows on a real search (1 credit), so that is opt-in."""
    kid = key_id(key)
    try:
        a = (http.get_json("https://api.tavily.com/usage", key).get("account") or {})
        lim = a.get("plan_limit") or 0
        left = max(0, lim - (a.get("plan_usage") or 0))
        if left > 0 and live_search:
            http.post_json("https://api.tavily.com/search", {"query": "test", "max_results": 1}, key)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return KeyStatus(kid, "tavily", "dead", checked_at=_now())
        if e.code in (432, 433, 429):
            return KeyStatus(kid, "tavily", "out", 0, None, "", _now())
        return KeyStatus(kid, "tavily", "error", checked_at=_now())
    except Exception:
        return KeyStatus(kid, "tavily", "error", checked_at=_now())
    return KeyStatus(kid, "tavily", "usable" if left > 0 else "out", float(left), float(lim), "", _now())


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def save_status(con: sqlite3.Connection, s: KeyStatus) -> None:
    if s.state == "error":       # network trouble: keep the last known balance, only record that the check failed
        con.execute("UPDATE key_status SET state='error', checked_at=? WHERE key_prefix=? AND provider=?", (s.checked_at, s.key_id, s.provider))
        if con.execute("SELECT changes()").fetchone()[0]:
            return
    con.execute("INSERT INTO key_status (key_prefix, provider, remaining, cap, resets, state, checked_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(key_prefix, provider) DO UPDATE SET remaining=excluded.remaining, cap=excluded.cap, resets=excluded.resets, "
                "state=excluded.state, checked_at=excluded.checked_at",
                (s.key_id, s.provider, s.remaining, s.cap, s.resets, s.state, s.checked_at))


def check_all(con: sqlite3.Connection, floor: float = APIFY_FLOOR, live_tavily: bool = False) -> list[KeyStatus]:
    demo = is_demo(con)
    ap, tv = load_keys("apify", demo), load_keys("tavily", demo)
    with ThreadPoolExecutor(8) as ex:
        out = list(ex.map(lambda k: check_apify(k, floor, demo), ap)) + list(ex.map(lambda k: check_tavily(k, live_tavily), tv))
    for s in out:
        save_status(con, s)
    return out


def statuses(con: sqlite3.Connection, provider: str | None = None) -> list[sqlite3.Row]:
    q = "SELECT * FROM key_status" + (" WHERE provider=?" if provider else "") + " ORDER BY provider, remaining DESC"
    return con.execute(q, (provider,) if provider else ()).fetchall()


def age_s(ts: str | None) -> float:
    if not ts:
        return 1e9
    return (datetime.now(timezone.utc) - datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)).total_seconds()


def leased_ids(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT l.key_prefix FROM key_leases l JOIN jobs j ON j.id=l.job_id WHERE j.status IN ('queued','running')")}


def pick_key(con: sqlite3.Connection, provider: str = "apify", floor: float = APIFY_FLOOR, exclude: set[str] | None = None) -> KeyStatus | None:
    """Best key to use now: freshest check, balance at or above the floor, not leased by a live job, most credit first."""
    busy = leased_ids(con) | (exclude or set())
    known = {key_id(k) for k in load_keys(provider, is_demo(con))}
    for r in statuses(con, provider):
        if r["key_prefix"] in busy or r["key_prefix"] not in known or r["state"] != "usable":
            continue
        if provider == "apify" and (r["remaining"] or 0) < floor:
            continue
        if age_s(r["checked_at"]) > STALE_S:
            continue
        return KeyStatus(r["key_prefix"], provider, r["state"], r["remaining"], r["cap"], r["resets"] or "", r["checked_at"])
    return None


def usable_credit(con: sqlite3.Connection, floor: float = APIFY_FLOOR) -> float:
    return round(sum(r["remaining"] or 0 for r in statuses(con, "apify") if r["state"] == "usable" and (r["remaining"] or 0) >= floor), 2)


def mark_failed(con: sqlite3.Connection, kid: str, provider: str, http_code: int | None = None, message: str = "") -> str:
    """Rotate rule (SETUP s4): 401/403 -> dead; 429/432/433 or 'limit exceeded' -> out of credit. Returns the new state."""
    m = message.lower()
    state = "dead" if http_code in (401, 403) else ("out" if http_code in (429, 432, 433) or "limit exceeded" in m or "insufficient credit" in m else "error")
    con.execute("UPDATE key_status SET state=?, checked_at=? WHERE key_prefix=? AND provider=?", (state, _now(), kid, provider))
    return state


# ------------------------------------------------------------------ editing .env safely
def add_keys(provider: str, new_keys: list[str], env_path: Path | None = None, backup_dir: Path | None = None) -> tuple[int, Path]:
    """Append keys to the provider's variable in .env. Backs the old .env up OUTSIDE the repo first. Returns (count added, backup path). Never echoes keys."""
    env_path = Path(env_path or paths.ROOT / ".env")
    backup_dir = Path(backup_dir or os.environ.get("LPD_ENV_BACKUP_DIR") or Path.home() / "lpd_env_backups")
    if paths.ROOT.resolve() in backup_dir.resolve().parents or backup_dir.resolve() == paths.ROOT.resolve():
        raise ValueError("the .env backup folder must be outside the repository")
    prefix, var, _ = PROVIDERS[provider]
    keys = [k for k in dict.fromkeys(k.strip() for k in new_keys) if k.startswith(prefix)]
    if not keys:
        raise ValueError(f"no valid {provider} keys (they must start with '{prefix}')")
    text = env_path.read_text(encoding="utf-8-sig") if env_path.exists() else ""
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"env_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
    if env_path.exists():
        shutil.copy2(env_path, backup)
    lines, found, added = text.splitlines(), False, 0
    for i, line in enumerate(lines):
        if line.startswith(var + "="):
            have = split_keys(line.split("=", 1)[1].split(" #")[0])
            fresh = [k for k in keys if k not in have]
            added = len(fresh)
            lines[i] = f"{var}=" + ",".join(have + fresh)
            found = True
    if not found:
        lines.append(f"{var}=" + ",".join(keys))
        added = len(keys)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[var] = ",".join(split_keys(os.environ.get(var, "")) + [k for k in keys if k not in split_keys(os.environ.get(var, ""))])
    return added, backup
