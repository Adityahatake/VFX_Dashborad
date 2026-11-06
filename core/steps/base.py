"""Step interface, context and registry. Every step (built-in or custom) implements Step and registers with @register."""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

Kind = Literal["free", "paid", "llm", "write"]


class Cancelled(Exception):
    """Raised by ctx.check_cancel() when the user asked the job to stop."""


class LeaseBusy(Exception):
    pass


@dataclass
class CostEstimate:
    max_usd: float = 0.0
    provider: str = ""          # "apify" | "tavily" | "llm" | ""
    key_required: bool = False
    note: str = ""


@dataclass
class StepResult:
    status: Literal["done", "partial"] = "done"
    counts: dict[str, int] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)   # file names inside the workdir
    actual_cost: float = 0.0
    message: str = ""


class NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepContext:
    """What a step sees. Built by the worker; tests build one directly."""

    def __init__(self, *, job_id: int, cycle_id: int | None, workdir: Path, job_dir: Path, log: Callable[[str], None],
                 is_cancelled: Callable[[], bool], lease: Callable[[str], Any], sheet=None, llm=None):
        self.job_id, self.cycle_id = job_id, cycle_id
        self.workdir, self.job_dir = workdir, job_dir
        self._log, self._is_cancelled, self._lease = log, is_cancelled, lease
        self.sheet, self.llm = sheet, llm      # filled in by later phases (None until then)
        self.workdir.mkdir(parents=True, exist_ok=True)

    def log(self, msg: str) -> None:
        self._log(msg)

    def check_cancel(self) -> None:
        if self._is_cancelled():
            raise Cancelled()

    def lease_key(self, key_prefix: str):
        """`with ctx.lease_key("apify_ZoxD") as k:`: one job per key at a time; raises LeaseBusy if another live job holds it."""
        return self._lease(key_prefix)

    # -- checkpoint: a small JSON file next to the job log; resume() reads it back
    @property
    def _ckpt(self) -> Path:
        return self.job_dir / "checkpoint.json"

    def load_checkpoint(self) -> dict:
        try:
            return json.loads(self._ckpt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_checkpoint(self, data: dict) -> None:
        tmp = self._ckpt.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(self._ckpt)     # atomic: a kill mid-write never leaves a half file


class Step:
    id: ClassVar[str]
    kind: ClassVar[Kind] = "free"
    title: ClassVar[str] = ""
    params_model: ClassVar[type[BaseModel]] = NoParams

    def estimate_cost(self, ctx: StepContext | None, params: BaseModel) -> CostEstimate:
        return CostEstimate()

    def run(self, ctx: StepContext, params: BaseModel) -> StepResult:
        raise NotImplementedError

    def resume(self, ctx: StepContext, params: BaseModel) -> StepResult:
        """Continue from the checkpoint if there is one. Default: run again (steps must be idempotent or override this)."""
        return self.run(ctx, params)


_REGISTRY: dict[str, Step] = {}
_BROKEN: dict[str, str] = {}      # step module -> error text (custom steps; shown as error cards)


def register(cls):
    _REGISTRY[cls.id] = cls()
    return cls


def get_step(step_id: str) -> Step:
    if step_id not in _REGISTRY:
        raise KeyError(f"unknown step '{step_id}'")
    return _REGISTRY[step_id]


def all_steps() -> dict[str, Step]:
    return dict(_REGISTRY)


def broken_steps() -> dict[str, str]:
    return dict(_BROKEN)
