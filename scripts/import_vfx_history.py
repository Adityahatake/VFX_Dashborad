"""One-time, repeatable import of the VFX repo's history, READ-ONLY on the VFX side. Safe to rerun: nothing is duplicated.

  py scripts/import_vfx_history.py [--vfx <path to VFX repo>] [--pipeline vfx_genai] [--dry-run]

Imports into SQLite (for dedupe and history):
  - every domain in pool_*.json            -> known_domains (status 'pooled'), and copies the pool file to data/<pipeline>/pools/ (for pool_match)
  - every domain in *_crawl.jsonl          -> known_domains (status 'crawled')
  - company names from *rejected*.csv, candidates_*.csv, roster_*.csv, verified_companies_*.csv -> known_names
  - spend_n1.log                           -> spend_ledger (cycle_id NULL, note 'imported:<hash>')
It prints counts only (no names, no keys)."""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import known, paths                       # noqa: E402
from core.db import open_db                          # noqa: E402
from core.textnorm import clean_domain               # noqa: E402

DEFAULT_VFX = Path(r"C:\Users\adity\OneDrive\Desktop\TRIAL\VFX")
SPEND = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\S+) (\S+) key=(\S+?)\.*\s+results=(\d+) est_cost=\$([\d.]+)")


def _csv_rows(path: str):
    with open(path, encoding="utf-8-sig", newline="") as f:
        yield from csv.reader(f)


def run(con, vfx: Path, pipeline: str, dry: bool = False) -> dict:
    data = vfx / "data"
    if not data.is_dir():
        raise SystemExit(f"{data} not found")
    c = dict.fromkeys(["pool_files", "pooled_domains", "crawled_domains", "names", "spend_lines", "spend_unparsed", "pools_copied"], 0)
    pooled, crawled, names = set(), set(), set()

    for f in sorted(glob.glob(str(data / "pool_*.json"))):
        try:
            items = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        c["pool_files"] += 1
        pooled |= {clean_domain(it.get("organization_primary_domain") or "") for it in items if isinstance(it, dict)}
        dest = paths.DATA_DIR / pipeline / "pools" / Path(f).name
        if not dest.exists():
            c["pools_copied"] += 1
            if not dry:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dest)                    # a copy; the VFX file is never touched
    for f in sorted(glob.glob(str(data / "*_crawl.jsonl"))):
        for line in open(f, encoding="utf-8"):
            try:
                crawled.add(clean_domain(json.loads(line)["domain"]))
            except Exception:
                pass
    for f in glob.glob(str(data / "*rejected*.csv")):
        for r in _csv_rows(f):
            if r and r[0].strip():
                names.add(r[0])
                if "." in r[0] and " " not in r[0]:
                    crawled.add(clean_domain(r[0]))          # some rejected files list domains
    for pat in ("candidates_*.csv", "roster_*.csv", "verified_companies_*.csv"):
        for f in glob.glob(str(data / pat)):
            with open(f, encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    if r.get("company"):
                        names.add(r["company"])
                    if r.get("domain"):
                        crawled.add(clean_domain(r["domain"]))
    pooled.discard("")
    crawled.discard("")
    c["pooled_domains"], c["crawled_domains"], c["names"] = len(pooled), len(crawled), len(names)

    log = data / "spend_n1.log"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    spend_rows = []
    for ln in lines:
        m = SPEND.match(ln)
        if not m:
            c["spend_unparsed"] += bool(ln.strip())
            continue
        date, tag, actor, key, results, cost = m.groups()
        spend_rows.append((date, tag, actor, key[:24], float(cost), int(results), "imported:" + hashlib.sha1(ln.encode()).hexdigest()[:16]))
    c["spend_lines"] = len(spend_rows)
    if dry:
        return c

    known.add_domains(con, pipeline, pooled, "pooled", "vfx_import")
    known.add_domains(con, pipeline, crawled, "crawled", "vfx_import")
    for n in names:
        known.add_name(con, pipeline, n, "vfx_import")
    for date, tag, actor, key, cost, results, note in spend_rows:
        if not con.execute("SELECT 1 FROM spend_ledger WHERE note=?", (note,)).fetchone():
            con.execute("INSERT INTO spend_ledger (ts, cycle_id, step_id, source, kind, key_prefix, est_max_usd, actual_usd, results, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (date + " 00:00:00", None, tag, actor, "apify", key, cost, cost, results, note))
    return c


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--vfx", type=Path, default=DEFAULT_VFX)
    ap.add_argument("--pipeline", default="vfx_genai")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    con = open_db()
    con.execute("INSERT OR IGNORE INTO pipelines (name, yaml_path) VALUES (?, ?)", (a.pipeline, str(paths.PIPELINES_DIR / a.pipeline / "pipeline.yaml")))
    res = run(con, a.vfx, a.pipeline, a.dry_run)
    print(("DRY RUN " if a.dry_run else "imported ") + json.dumps(res))
    if not a.dry_run:
        print("known domains:", con.execute("SELECT COUNT(*) FROM known_domains WHERE pipeline=?", (a.pipeline,)).fetchone()[0],
              "| known names:", con.execute("SELECT COUNT(*) FROM known_names WHERE pipeline=?", (a.pipeline,)).fetchone()[0],
              "| imported spend rows:", con.execute("SELECT COUNT(*) FROM spend_ledger WHERE note LIKE 'imported:%'").fetchone()[0])
