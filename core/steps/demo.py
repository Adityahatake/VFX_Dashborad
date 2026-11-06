"""A harmless fake step used to demo and test the jobs engine: sleeps in ticks, checkpoints, honours cancel. Costs nothing."""
from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field

from .base import CostEstimate, Step, StepContext, StepResult, register


class DemoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_s: int = Field(120, ge=1, le=3600)
    tick_s: float = Field(2.0, gt=0, le=60)
    lease_key: str | None = None      # e.g. "demo_key" to test one-job-per-key
    fail_at: int | None = None        # tick number at which to raise, to test failure handling


class DemoPaidParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_result: int = Field(25, ge=1, le=100_000)
    price_per_result: float = Field(0.003, gt=0)
    actual_results: int | None = None     # what the fake run "returns" (default: 80% of max_result)
    seconds: float = Field(6.0, gt=0, le=120)


@register
class DemoPaid(Step):
    """Mock of a paid Apify run: estimate = price x max_result, takes a key under a lease, records spend. No network, no real cost."""
    id = "demo_paid"
    kind = "paid"
    title = "Demo: mocked paid step"
    params_model = DemoPaidParams

    def estimate_cost(self, ctx, params: DemoPaidParams) -> CostEstimate:
        return CostEstimate(max_usd=round(params.max_result * params.price_per_result, 6), provider="apify", key_required=True,
                            note=f"{params.max_result} results x ${params.price_per_result}")

    def run(self, ctx: StepContext, params: DemoPaidParams) -> StepResult:
        est = self.estimate_cost(ctx, params).max_usd
        with ctx.use_key("apify") as (kid, _secret):
            ctx.log(f"mock paid run on key {kid}: max ${est:.3f}")
            for i in range(int(params.seconds)):
                ctx.check_cancel()
                time.sleep(1)
            n = params.actual_results if params.actual_results is not None else int(params.max_result * 0.8)
            cost = round(n * params.price_per_result, 6)
            ctx.record_spend(source="demo_actor", est_max_usd=est, actual_usd=cost, results=n, key_id=kid, note="mock")
        return StepResult(counts={"results": n}, actual_cost=cost, message=f"{n} results for ${cost:.3f} (mock)")


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
