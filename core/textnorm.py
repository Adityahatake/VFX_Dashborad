"""Name and domain normalisation, ported from the VFX repo's common.py (norm, ntoks, domain_is_known)."""
from __future__ import annotations

import re
import unicodedata


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().casefold()


def norm(s: str) -> str:
    """Company-name key: accents folded, punctuation dropped, legal/filler words removed."""
    s = re.sub(r"[^a-z0-9 ]", " ", _ascii(s))
    s = re.sub(r"\b(ltd|inc|llc|gmbh|studios?|films?|productions?|media|group|co|company|the|ai|agency)\b", " ", s)
    return " ".join(s.split())


def squash(s: str) -> str:
    return norm(s).replace(" ", "")


def ntoks(s: str) -> list[str]:
    return [t for t in re.sub(r"[^a-z0-9 ]", " ", _ascii(s)).split() if t]


# Words that domains glue onto a company name ("glassyfilms.com", "mad-studio.ai", "detroit.paris").
DOM_FILLER = r"studios?|films?|productions?|production|media|creative|agency|digital|official|group|hq|ai|the|tv|video|visual|lab|labs|made|world"


def clean_domain(url_or_domain: str) -> str:
    d = re.sub(r"^https?://", "", (url_or_domain or "").strip().lower()).split("/")[0].split(":")[0]
    return d.removeprefix("www.").rstrip(".")


def domain_is_known(domain: str, known: set[str]) -> bool:
    """True if a domain looks like a known company: strip TLD and filler words, then match exactly or by prefix (5+ chars)."""
    parts = clean_domain(domain).split(".")
    stem = parts[-3] if len(parts) > 2 and parts[-2] in ("co", "com") else parts[0]
    s = re.sub(r"[^a-z0-9]", "", stem)
    core = s
    for _ in range(3):                    # peel filler words off either end only ("humainmade" keeps "humain")
        core = re.sub(rf"^({DOM_FILLER})(?=.{{3}})|(?<=.{{3}})({DOM_FILLER})$", "", core)
    if re.sub(r"[^a-z0-9]", "", ".".join(parts)) in known:
        return True                       # the domain itself was logged as crawled / verified / rejected
    for k in (s, core):
        if k in known:
            return True
        if len(k) >= 5 and any(n.startswith(k) or (len(n) >= 5 and k.startswith(n)) for n in known):
            return True
    return False
