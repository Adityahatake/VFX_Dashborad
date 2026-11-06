"""Reading public web pages (ported from the VFX evidence.py). Steps call these through the module, so tests monkeypatch `web.fetch`."""
from __future__ import annotations

import ipaddress
import re
import ssl
import urllib.request
from urllib.parse import urljoin, urlparse

# Certificates are not checked: we only read public pages and expired certificates are common on small studio sites.
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0"
MAX_BYTES = 600_000


def is_public_url(u: str) -> bool:
    """Only http(s) to public hosts: a harvested link can never point the crawler at this machine or the local network."""
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    h = p.hostname.lower()
    if h == "localhost" or h.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        ip = ipaddress.ip_address(h)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        return True


def fetch(u: str, timeout: float = 12) -> tuple[str, str]:
    """(final_url, html) or (u, '') on any error or a non-public target."""
    if not is_public_url(u):
        return u, ""
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=timeout, context=_CTX)
        if not is_public_url(r.geturl()):              # a redirect into the local network is dropped
            return u, ""
        return r.geturl(), r.read(MAX_BYTES).decode("utf-8", "ignore")
    except Exception:
        return u, ""


def text(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", h)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).replace("&amp;", "&").replace("&nbsp;", " ")


def internal_links(u: str, h: str, keep, limit: int) -> list[str]:
    host = urlparse(u).netloc
    out: list[str] = []
    for m in re.finditer(r'href=["\']([^"\'#?]+)', h):
        link = urljoin(u, m.group(1))
        p = urlparse(link)
        if p.netloc != host or link in out or re.search(r"\.(jpg|png|pdf|mp4|css|js|svg|webp|woff2?)$", p.path, re.I):
            continue
        if keep(p.path):
            out.append(link)
    return out[:limit]
