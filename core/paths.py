"""Central paths and .env loading. Nothing secret is stored outside .env."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("LPD_ROOT", Path(__file__).resolve().parent.parent))
PIPELINES_DIR = Path(os.environ.get("LPD_PIPELINES", ROOT / "pipelines"))
DATA_DIR = Path(os.environ.get("LPD_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "dashboard.sqlite"


def load_env(path: Path | None = None) -> None:
    """Load .env into os.environ without overriding variables that are already set."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            v = v.split(" #")[0].strip().strip('"').strip("'")
            if v:
                os.environ.setdefault(k.strip(), v)


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def pipeline_dirs() -> list[Path]:
    """Pipeline folders. A folder starting with '_' (for example _archived) is never a pipeline."""
    return sorted(p for p in PIPELINES_DIR.iterdir() if not p.name.startswith("_") and (p / "pipeline.yaml").exists()) if PIPELINES_DIR.exists() else []
