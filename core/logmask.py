"""Mask anything that looks like an API key, in strings and in log records."""
from __future__ import annotations

import logging
import re

KEY_RX = re.compile(r"(apify_api_|tvly-|gsk_|sk-ant-)[A-Za-z0-9_\-]{6,}")
PEM_RX = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)


def mask(text: str) -> str:
    text = PEM_RX.sub("[private key removed]", text)
    return KEY_RX.sub(lambda m: m.group(0)[: len(m.group(1)) + 4] + "…", text)


def prefix(key: str, n: int = 6) -> str:
    """Display form of a key: first n characters plus an ellipsis."""
    return key[:n] + "…" if key else ""


class MaskFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask(str(record.getMessage()))
        record.args = ()
        if record.exc_info:
            record.exc_text = mask(logging.Formatter().formatException(record.exc_info))
        return True


def install(logger: logging.Logger | None = None) -> None:
    (logger or logging.getLogger()).addFilter(MaskFilter())
