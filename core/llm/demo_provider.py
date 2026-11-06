"""Demo-mode LLM: deterministic canned answers, no network, no key. It deliberately behaves like the real thing in the ways that matter for testing the
app: it quotes verbatim from the matched sentences, simulates prompt-cache usage (first call writes the system prompt, later calls read it), reports
token counts, and computes cost from the price table, so spend, the cap and the checks all exercise real code paths. It also sometimes proposes
'High' confidence so the downgrade rule can be seen. NOT a model: its 'verdicts' mean nothing."""
from __future__ import annotations

import json
import re

from .base import LLMResult, approx_tokens, cost_of


class DemoProvider:
    name = "demo"

    def __init__(self, prices: dict[str, dict[str, float]] | None = None):
        self._prices, self._seen_system = prices or {}, set()

    def complete_json(self, *, model: str, system: str, user: str, schema: dict, max_tokens: int, effort: str) -> LLMResult:
        r = LLMResult(model=model, provider=self.name, stop_reason="end_turn", latency_ms=1)
        first = system not in self._seen_system
        self._seen_system.add(system)
        st = approx_tokens(system)
        r.cache_write_tokens, r.cache_read_tokens = (st, 0) if first else (0, st)
        r.input_tokens = approx_tokens(user)
        props = schema["properties"]
        if "qualifies" in props:
            m = re.search(r"<matched_sentences>\n(.*?)\n</matched_sentences>", user, re.S)
            sent = re.sub(r"^- ", "", (m.group(1).splitlines() or [""])[0]).strip() if m else ""
            ok = bool(re.search(r"AI-generated|generative AI|Midjourney|Runway|ComfyUI", sent, re.I)) and bool(re.search(r"client|campaign|spot|commercial", sent, re.I))
            out = {"qualifies": "yes" if ok else "unsure", "named_client": "Demo Client" if ok else "", "ai_used_to_make_work": ok, "quote": sent[:280] if ok else "",
                   "country": "Germany" if ok else "", "company_type": "production studio" if ok else "", "reject_reason_code": "",
                   "confidence": 0.8 if ok else 0.2, "reason": "Demo answer: AI wording next to a client cue in the matched sentence." if ok else "Demo answer: not enough evidence."}
        else:
            t = (re.search(r"Person's title.*?: (.*)", user) or [None, ""])[1]
            out = {"role_family": "ceo" if re.search(r"founder|ceo|owner", t, re.I) else "creative" if re.search(r"creative", t, re.I) else "other",
                   "priority": "P1" if re.search(r"founder|ceo|owner", t, re.I) else "P2", "why_this_person": f"Demo draft: {t or 'this person'} owns decisions on the studio's AI-assisted client work.",
                   "commercial_route": "R1", "primary_commercial_problem": "Demo hypothesis: the studio may want a repeatable AI production workflow for client film work.",
                   "confidence": "High", "confidence_reason": "Demo: pretends the title was confirmed (the app must downgrade this).", "flags": ["demo provider: ignore the content"]}
        r.raw_text = json.dumps(out)
        r.parsed = out
        r.output_tokens = approx_tokens(r.raw_text)
        r.cost_usd = cost_of(r, self._prices.get(model))
        return r
