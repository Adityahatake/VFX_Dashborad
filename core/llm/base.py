"""LLM provider interface and cost accounting. A provider turns (system, user, JSON schema) into an LLMResult and never raises for
API problems: failures come back as `error` so a batch can record them and carry on. Prices live in settings (editable); the defaults
below are Anthropic's published first-party list prices as of the Claude API reference used for this build (cached 2026-10-06)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# USD per 1M tokens: input, output, cache read, cache write (5-minute cache: 1.25x input). Editable in Settings; never trusted blindly.
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read": 0.20, "cache_write": 2.50},
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "cache_read": 0.01, "cache_write": 0.125},
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_read": 0.20, "cache_write": 5.00},
}


@dataclass
class LLMResult:
    parsed: dict | None = None
    raw_text: str = ""
    model: str = ""
    provider: str = ""
    input_tokens: int = 0              # uncached input tokens
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    stop_reason: str = ""
    error: str | None = None           # e.g. "refusal:cyber", "max_tokens", "rate_limited", "parse_error"
    cost_usd: float | None = None
    request_id: str = ""


class LLMProvider(Protocol):
    name: str

    def complete_json(self, *, model: str, system: str, user: str, schema: dict, max_tokens: int, effort: str) -> LLMResult: ...


def cost_of(r: LLMResult, prices: dict[str, float] | None) -> float | None:
    """Dollar cost of one call, or None when the model has no price (the caller must then refuse to run: the cap could not be enforced)."""
    if not prices:
        return None
    return round((r.input_tokens * prices["in"] + r.output_tokens * prices["out"] + r.cache_read_tokens * prices["cache_read"]
                  + r.cache_write_tokens * prices["cache_write"]) / 1_000_000, 6)


def approx_tokens(text: str) -> int:
    """A deliberately pessimistic estimate (3 characters per token) used only for pre-run maximum-cost estimates."""
    return int(len(text) / 3) + 1
