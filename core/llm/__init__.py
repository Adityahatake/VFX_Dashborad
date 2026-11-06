"""LLM assist (optional). Active only when ALL of these hold: ANTHROPIC_API_KEY is set, the global Settings toggle is on, the pipeline's llm block
is enabled with provider 'anthropic', and the model has a price (so the spend cap can be enforced). Otherwise `resolve` says why not and every
screen falls back to manual review. The LLM only suggests; nothing it produces approves, appends or deletes anything."""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass

from ..config import PipelineConfig
from ..db import get_setting
from .base import DEFAULT_PRICES, LLMProvider


@dataclass
class Resolved:
    provider: LLMProvider | None
    model: str
    cap_usd: float
    prices: dict[str, float] | None
    reason: str                    # why it is off (empty when on)

    @property
    def on(self) -> bool:
        return self.provider is not None


def price_table(con: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """Defaults overridden by the Settings price table (JSON in settings key llm.prices)."""
    t = {m: dict(p) for m, p in DEFAULT_PRICES.items()}
    try:
        for m, p in json.loads(get_setting(con, "llm.prices", "{}") or "{}").items():
            t[m] = {**t.get(m, {}), **{k: float(v) for k, v in p.items()}}
    except (ValueError, TypeError, AttributeError):
        pass
    return t


def resolve(con: sqlite3.Connection, cfg: PipelineConfig | None, provider_factory=None) -> Resolved:
    off = lambda why: Resolved(None, "", 0.0, None, why)
    if cfg is None:
        return off("no pipeline")
    if get_setting(con, "llm.enabled", "0") != "1":
        return off("LLM assist is off (Settings toggle): manual mode")
    if not cfg.llm.enabled:
        return off("LLM assist is disabled for this pipeline (llm.enabled in pipeline.yaml)")
    if cfg.llm.provider == "groq":
        return off("provider 'groq' is not implemented in this build (Anthropic only)")
    if cfg.llm.provider != "anthropic":
        return off("no LLM provider configured for this pipeline: manual mode")
    from .. import keys as _keys
    demo = _keys.is_demo(con)                               # demo mode: canned answers, no key, no network
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key and provider_factory is None and not demo:
        return off("ANTHROPIC_API_KEY is not set: manual mode")
    model = get_setting(con, "llm.model", "") or cfg.llm.model
    prices = price_table(con).get(model)
    if not prices:
        return off(f"no price set for model '{model}': add it in Settings so the LLM cap can be enforced")
    cap = min(cfg.llm.cycle_cap_usd, float(get_setting(con, "llm.cycle_cap_usd", str(cfg.llm.cycle_cap_usd)) or cfg.llm.cycle_cap_usd))
    if provider_factory is not None:                    # tests inject a fake provider; the real one is built only with a key
        return Resolved(provider_factory(), model, cap, prices, "")
    if demo:
        from .demo_provider import DemoProvider
        return Resolved(DemoProvider(price_table(con)), model, cap, prices, "")
    from .anthropic_provider import AnthropicProvider
    return Resolved(AnthropicProvider(api_key=key, prices=price_table(con)), model, cap, prices, "")
