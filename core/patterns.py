"""Turns the pipeline's evidence lists (plain words) into the regexes the crawler uses. The VFX regexes were hard-coded; here they come from config.

Term syntax (in evidence.strong_terms / client_cues):
  separators   "AI-generated" matches "AI-generated", "AI generated"
  `*`          matches the rest of a word:  "KI-generiert*" matches "KI-generierte"
  `{Brand}`    matches a capitalised word:  "for {Brand}" matches "for Nike"
Strong terms must not run into a longer word ("Kling" does not match "Klinger"); client cues are plain substrings ("project" matches "projects")."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Evidence


BRAND = r"(?-i:[A-Z][a-zà-ÿ]+)"          # a really capitalised word, even though the surrounding pattern ignores case


def _piece(s: str) -> str:
    """Words joined by a flexible separator; leading / trailing whitespace (next to {Brand} or *) is kept as `\\s+`."""
    core = [re.escape(w) for w in re.split(r"[-\s]+", s) if w != ""]
    body = r"[-\s]+".join(core)
    return (r"\s+" if s[:1].isspace() else "") + body + (r"\s+" if s[-1:].isspace() and core else "")


def _body(term: str) -> str:
    return BRAND.join(r"\w*".join(_piece(x) for x in part.split("*")) for part in term.split("{Brand}"))


def term_regex(term: str, edges: bool) -> str:
    t = term.strip()
    b = _body(t)
    if not edges:
        return b
    start = r"(?<![A-Za-z])" if t[:1].isalnum() else ""
    end = "" if t.endswith("*") else (r"(?![a-z])" if t[-1:].isalpha() else "")
    return f"{start}{b}{end}"


@dataclass
class Patterns:
    strong: re.Pattern
    cue: re.Pattern
    false: re.Pattern | None


def build(ev: Evidence) -> Patterns:
    if not ev.strong_terms:
        raise ValueError("evidence.strong_terms is empty: the crawler would find nothing")
    strong = re.compile("|".join(term_regex(t, True) for t in ev.strong_terms), re.I)
    cue = re.compile("|".join(term_regex(t, False) for t in ev.client_cues) or r"(?!x)x", re.I)
    false = re.compile("|".join(f"(?:{p})" for p in ev.false_positive_patterns), re.I) if ev.false_positive_patterns else None
    return Patterns(strong, cue, false)


def evidence_hits(text: str, pat: Patterns, window=(160, 200), limit: int = 5, seen: set | None = None) -> list[str]:
    """Sentences (windows of text) where strong AI wording sits next to a client cue, minus the false-positive patterns.
    Pass the same `seen` set across the pages of one site so a repeated sentence counts once."""
    out = []
    seen = set() if seen is None else seen
    for m in pat.strong.finditer(text):
        s = text[max(0, m.start() - window[0]):m.end() + window[1]]
        if (pat.false and pat.false.search(s)) or not pat.cue.search(s) or s[100:180] in seen:
            continue
        seen.add(s[100:180])
        out.append(s)
        if len(out) >= limit:
            break
    return out
