"""A harmless fake step used to demo and test the jobs engine: sleeps in ticks, checkpoints, honours cancel. Costs nothing."""
from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field

from .base import Step, StepContext, StepResult, register


class DemoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_s: int = Field(120, ge=1, le=3600)
    tick_s: float = Field(2.0, gt=0, le=60)
    lease_key: str | None = None      # e.g. "demo_key" to test one-job-per-key
    fail_at: int | None = None        # tick number at which to raise, to test failure handling


@register
class DemoSlow(Step):
    id = "demo_slow"
    kind = "free"
    title = "Demo: slow fake step"
    params_model = DemoParams

    def run(self, ctx: StepContext, params: DemoParams) -> StepResult:
        return self._loop(ctx, params, start=0)

    def resume(self, ctx: StepContext, params: DemoParams) -> StepResult:
        done = int(ctx.load_checkpoint().get("done", 0))
        ctx.log(f"resuming from checkpoint: {done} ticks already done")
        return self._loop(ctx, params, start=done)

    def _loop(self, ctx, p: DemoParams, start: int) -> StepResult:
        total = max(1, int(p.duration_s / p.tick_s))
        def body():
            for i in range(start, total):
                ctx.check_cancel()
                if p.fail_at is not None and i == p.fail_at:
                    raise RuntimeError(f"demo failure at tick {i}")
                time.sleep(p.tick_s)
                ctx.save_checkpoint({"done": i + 1})
                ctx.log(f"tick {i + 1}/{total}")
        if p.lease_key:
            with ctx.lease_key(p.lease_key):
                body()
        else:
            body()
        (ctx.workdir / "demo_out.txt").write_text(f"finished {total} ticks\n", encoding="utf-8")
        return StepResult(counts={"ticks": total}, artifacts=["demo_out.txt"], message="finished")
