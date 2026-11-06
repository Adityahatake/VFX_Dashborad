import logging

from core.logmask import MaskFilter, mask, prefix

APIFY = "apify_api_" + "A1b2C3d4E5f6G7h8"
TAV = "tvly-" + "dev-abcdef123456"
GROQ = "gsk_" + "abcdef1234567890"


def test_mask_keys():
    for k in (APIFY, TAV, GROQ):
        out = mask(f"token={k} end")
        assert k not in out and "…" in out


def test_mask_private_key():
    pem = "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"
    assert "abc" not in mask(pem)


def test_prefix():
    assert prefix(APIFY) == "apify_…"
    assert prefix("") == ""


def test_filter_on_handler(caplog):
    h = logging.Handler()
    seen = []
    h.emit = lambda r: seen.append(r.getMessage())
    h.addFilter(MaskFilter())
    lg = logging.getLogger("t")
    lg.addHandler(h)
    lg.warning("using %s", APIFY)
    assert seen and APIFY not in seen[0]
