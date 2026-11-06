"""Anthropic provider (official SDK). One Messages call per item:
  * the system prompt (rubric + SOP) carries cache_control so repeated calls read it from the cache
  * structured output through output_config.format (JSON schema) with a low effort level; no temperature (rejected on Sonnet 5.5), no prefill
  * a refusal or max_tokens stop is reported as an error, never as an answer
Errors never raise: they come back on LLMResult.error so a batch can record them and continue. The SDK itself retries 408/409/429/5xx twice."""
from __future__ import annotations

import time

from .base import LLMResult, cost_of
from .checks import extract_json


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None, client=None, prices: dict[str, dict[str, float]] | None = None):
        if client is None:
            import anthropic                       # optional dependency: only needed for live use
            client = anthropic.Anthropic(api_key=api_key, max_retries=2)
        self._client, self._prices = client, prices or {}

    def complete_json(self, *, model: str, system: str, user: str, schema: dict, max_tokens: int, effort: str) -> LLMResult:
        import anthropic
        t0 = time.time()
        r = LLMResult(model=model, provider=self.name)
        try:
            resp = self._client.messages.create(
                model=model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.RateLimitError:
            r.error = "rate_limited"
        except anthropic.AuthenticationError:
            r.error = "auth_error: check ANTHROPIC_API_KEY"
        except anthropic.BadRequestError as e:
            r.error = f"bad_request: {str(getattr(e, 'message', e))[:200]}"
        except anthropic.APIStatusError as e:
            r.error = f"api_error_{e.status_code}"
        except anthropic.APIConnectionError:
            r.error = "connection_error"
        else:
            r.request_id = getattr(resp, "_request_id", "") or getattr(resp, "id", "")
            r.stop_reason = resp.stop_reason or ""
            u = resp.usage
            r.input_tokens, r.output_tokens = u.input_tokens or 0, u.output_tokens or 0
            r.cache_read_tokens, r.cache_write_tokens = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
            r.cost_usd = cost_of(r, self._prices.get(model))
            if resp.stop_reason == "refusal":
                sd = getattr(resp, "stop_details", None)
                r.error = "refusal:" + (getattr(sd, "category", None) or "unspecified")
            elif resp.stop_reason == "max_tokens":
                r.error = "max_tokens"
            else:
                r.raw_text = next((b.text for b in resp.content if b.type == "text"), "")
                r.parsed = extract_json(r.raw_text)
                if r.parsed is None:
                    r.error = "parse_error"
        r.latency_ms = int((time.time() - t0) * 1000)
        return r
