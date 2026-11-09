"""Import API keys from the shared 'Api keys and passwords' sheet into .env, without the keys ever being printed.
  * Only the key column and the Live Status column of each tab are requested from Google (the sheet also holds emails and passwords: not read).
  * Only keys the sheet itself marks USABLE are kept, and only keys with the provider's expected prefix.
  * Output (and logs) show counts and short key ids only. Writing .env goes through keys.add_keys, which backs the old .env up outside the repo.
Column layout follows the VFX keys_sheet.py: Apify and Apify Accounts keep keys in column D and the live status in column F; Tavily uses A and C."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import keys as keymod
from .sheets import SheetsClient, quote_tab

LAYOUT = {"apify": {"Apify": ("D", "F"), "Apify Accounts": ("D", "F")}, "tavily": {"Tavily": ("A", "C")}}
MAX_ROWS = 2000


@dataclass
class Candidate:
    provider: str
    tab: str
    row: int
    key: str
    status: str


@dataclass
class Selection:
    provider: str
    keys: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _column(client: SheetsClient, tab: str, col: str) -> list[str]:
    """One column from row 2 down, aligned by row (empty cells become '')."""
    vals = client.get_values(f"{quote_tab(tab)}!{col}2:{col}{MAX_ROWS}")
    return [(r[0].strip() if r else "") for r in vals]


def read_candidates(client: SheetsClient, provider: str) -> tuple[list[Candidate], list[str]]:
    out, notes = [], []
    for tab, (kc, sc) in LAYOUT[provider].items():
        try:
            ks, ss = _column(client, tab, kc), _column(client, tab, sc)
        except Exception as e:                                         # a missing tab must not stop the others
            notes.append(f"tab '{tab}': not read ({type(e).__name__})")
            continue
        for i, k in enumerate(ks):
            if k:
                out.append(Candidate(provider, tab, i + 2, k, ss[i] if i < len(ss) else ""))
    return out, notes


def select_usable(cands: list[Candidate], provider: str, existing: set[str] | None = None) -> Selection:
    prefix = keymod.PROVIDERS[provider][0]
    sel = Selection(provider)
    seen, existing = set(), existing or set()
    c = dict.fromkeys(["rows_with_a_key", "wrong_prefix", "not_marked_usable", "duplicates", "already_in_env", "selected"], 0)
    for x in cands:
        c["rows_with_a_key"] += 1
        if not x.key.startswith(prefix):
            c["wrong_prefix"] += 1
        elif not x.status.upper().startswith("USABLE"):
            c["not_marked_usable"] += 1
        elif x.key in seen:
            c["duplicates"] += 1
        elif x.key in existing:
            c["already_in_env"] += 1
            seen.add(x.key)
        else:
            seen.add(x.key)
            sel.keys.append(x.key)
            c["selected"] += 1
    sel.counts = c
    stale = [x for x in cands if x.status.upper().startswith("USABLE")]
    dates = [m.group(1) for x in stale if (m := re.search(r"checked (\d{4}-\d{2}-\d{2})", x.status))]
    if dates:
        sel.notes.append(f"the sheet's 'USABLE' marks were last checked between {min(dates)} and {max(dates)}: balances are re-checked live before any use")
    return sel


def describe(sel: Selection) -> list[str]:
    """Printable summary: counts and short ids only."""
    lines = [f"{sel.provider}: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sel.counts.items())]
    if sel.keys:
        lines.append("  would add: " + ", ".join(keymod.key_id(k) for k in sel.keys))
    lines += [f"  note: {n}" for n in sel.notes]
    return lines
