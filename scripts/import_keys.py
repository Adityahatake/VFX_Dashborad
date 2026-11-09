"""Import USABLE API keys from the keys sheet into .env. Prints counts and short key ids only, never a key.

  py scripts/import_keys.py                 # dry run (default): shows what would be added
  py scripts/import_keys.py --write         # adds them to .env (the old .env is backed up outside the repo first)
  py scripts/import_keys.py --provider apify --sheet <id>

Needs GOOGLE_APPLICATION_CREDENTIALS and KEYS_SHEET_ID (or --sheet) in .env. The sheet is read with a READ-ONLY token and only the key and
status columns are requested."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import keyimport, keys, paths                       # noqa: E402
from core.sheets import SCOPE_READONLY, GoogleSheets          # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["apify", "tavily"], default="apify")
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--write", action="store_true", help="actually add the keys to .env (default: dry run)")
    a = ap.parse_args(argv)
    paths.load_env()
    sid, cred = a.sheet or os.environ.get("KEYS_SHEET_ID", ""), os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not sid or not cred or not Path(cred).exists():
        print("need KEYS_SHEET_ID (or --sheet) and a GOOGLE_APPLICATION_CREDENTIALS file that exists")
        return 2
    client = GoogleSheets(sid, cred, scope=SCOPE_READONLY)
    cands, notes = keyimport.read_candidates(client, a.provider)
    sel = keyimport.select_usable(cands, a.provider, set(keys.load_keys(a.provider)))
    sel.notes += notes
    print("\n".join(keyimport.describe(sel)))
    if not a.write:
        print("dry run: nothing written. Add --write to add these keys to .env.")
        return 0
    if not sel.keys:
        print("nothing to add.")
        return 0
    n, backup = keys.add_keys(a.provider, sel.keys)
    print(f"added {n} key(s) to .env. Previous .env backed up to {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
