"""Duplicate / cap / country / evidence checks for rows about to be appended. Ported from VFX sheet_tools.py (name_key, url_key, state, check_rows);
columns, cap and excluded countries come from the pipeline config instead of being hard-coded."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .config import PipelineConfig
from .sheets import SheetsClient
from .textnorm import norm


def name_key(name: str) -> tuple:
    """First + last name, accents and German umlaut spellings folded (Pöcksteiner = Pocksteiner = Poecksteiner, Thorsten Jasper Weese = Thorsten Weese)."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().casefold()
    s = re.sub(r"(?<=[a-z])(ae|oe|ue)", lambda m: m.group(1)[0], s)
    t = re.sub(r"[^a-z ]", " ", s).split()
    return (t[0], t[-1].replace("mc", "mac")) if len(t) >= 2 else tuple(t)


def url_key(u: str) -> str:
    u = (u or "").strip().lower().split("?")[0].split("#")[0].rstrip("/")
    return re.sub(r"^https?://(www\.|[a-z]{2}\.)?", "", u)


def pad(r: list, n: int) -> list:
    return (list(r) + [""] * n)[:n]


COUNTRY_ALIASES = {"us": "united states", "usa": "united states", "u.s.": "united states", "u.s.a.": "united states", "uk": "united kingdom",
                   "great britain": "united kingdom", "england": "united kingdom", "scotland": "united kingdom", "wales": "united kingdom",
                   "uae": "united arab emirates", "korea": "south korea", "czechia": "czech republic", "holland": "netherlands", "the netherlands": "netherlands"}


def country_key(c: str) -> str:
    c = re.sub(r"\(.*?\)", "", c or "").strip().casefold()
    return COUNTRY_ALIASES.get(c, c)


@dataclass
class SheetState:
    names: set = field(default_factory=set)        # name keys on any checked tab
    pairs: set = field(default_factory=set)        # (name key, normalised company)
    urls: set = field(default_factory=set)
    count: dict = field(default_factory=dict)      # normalised company -> people on the WRITE tab
    warnings: list = field(default_factory=list)

    def add(self, header: list[str], row: list[str], cfg: PipelineConfig, on_write_tab: bool = True) -> None:
        d = cfg.output.dedupe
        r = dict(zip(header, pad(row, len(header))))
        nk, co = name_key(r.get(d.name_field, "")), norm(r.get(d.company_field, ""))
        self.names.add(nk)
        self.pairs.add((nk, co))
        for f in d.url_fields:
            if r.get(f):
                self.urls.add(url_key(r[f]))
        if on_write_tab:
            self.count[co] = self.count.get(co, 0) + 1


def read_state(client: SheetsClient, cfg: PipelineConfig) -> tuple[SheetState, list[list[str]]]:
    """Fresh read of every checked tab. Returns the state and the write tab's raw values (header included).
    Rows without both a name and a company (empty rows, stray markers) are skipped, never deleted."""
    st, wt, d = SheetState(), cfg.output.write_tab, cfg.output.dedupe
    write_vals: list[list[str]] = []
    for tab in cfg.output.tabs:
        v = client.get_values(tab.range)
        if tab.write:
            write_vals = v
        if not v:
            continue
        h = v[0]
        if d.name_field not in h or d.company_field not in h:
            st.warnings.append(f"tab '{tab.name}' has no '{d.name_field}'/'{d.company_field}' column: not used for duplicate checks")
            continue
        ni, ci = h.index(d.name_field), h.index(d.company_field)
        for r in v[1:]:
            r = pad(r, len(h))
            if not r[ni].strip() or not r[ci].strip():
                continue
            nk, co = name_key(r[ni]), norm(r[ci])
            st.names.add(nk)
            st.pairs.add((nk, co))
            for c in r:                                          # any cell holding a profile link counts (VFX behaviour)
                if any(m in c for m in d.profile_url_markers) or "x.com/" in c:
                    st.urls.add(url_key(c))
            if tab.write:
                st.count[co] = st.count.get(co, 0) + 1
    return st, write_vals


def check_rows(rows: list[list[str]], cfg: PipelineConfig, st: SheetState) -> tuple[list[list[str]], list[tuple[str, str, str]]]:
    """(ok rows, [(company, name, reason)]). Rows are judged in order, so two rows in one batch cannot both slip past the cap or the duplicate rule."""
    cols, d, cap = cfg.output.columns, cfg.output.dedupe, cfg.people.max_per_company
    excl = [re.compile(p, re.I) for p in cfg.countries.excluded_patterns]
    excl_names = {country_key(c) for c in cfg.countries.excluded}
    approved = {country_key(c) for c in cfg.countries.approved}
    ok, rej, seen_names, seen_company = [], [], set(), {}
    for raw in rows:
        r = pad(raw, len(cols))
        x = dict(zip(cols, r))
        nk, co, url = name_key(x[d.name_field]), norm(x[d.company_field]), x[d.url_fields[0]]
        country = x[d.country_field]
        why = ""
        if len(raw) != len(cols) or not x[d.name_field].strip() or not x[d.company_field].strip():
            why = "malformed row (wrong width, or name/company empty)"
        elif not any(m in url for m in d.profile_url_markers):
            why = "no personal profile URL"
        elif not x[d.evidence_field].strip():
            why = "empty evidence_source"
        elif country_key(country) in excl_names or any(p.search(country) for p in excl):
            why = f"excluded country ({country.strip()})"
        elif approved and country_key(country) not in approved:
            why = f"country not approved ({country.strip() or 'empty'})"
        elif any(url_key(x[f]) in st.urls for f in d.url_fields if x[f]):
            why = "same profile URL already on a tab"
        elif (nk, co) in st.pairs or nk in st.names or nk in seen_names:
            why = "same person already on a tab (any company, spelling variants folded)"
        elif st.count.get(co, 0) + seen_company.get(co, 0) >= cap:
            why = f"company already has {cap} people"
        if why:
            rej.append((x[d.company_field], x[d.name_field], why))
            continue
        seen_names.add(nk)
        seen_company[co] = seen_company.get(co, 0) + 1
        ok.append(r)
    return ok, rej


def own_urls(rows: list[list[str]], cfg: PipelineConfig) -> set[str]:
    i = cfg.output.columns.index(cfg.output.dedupe.url_fields[0])
    return {url_key(r[i]) for r in rows if len(r) > i}
