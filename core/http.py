"""One small urllib wrapper so every network call is easy to mock. Reads retry on network errors and 429/5xx; writes never retry."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def request_json(url: str, *, key: str | None = None, body: dict | None = None, timeout: float = 40):
    """GET (body None) or POST (body given). Returns parsed JSON. HTTPError propagates so callers can rotate on 401/403/429/432."""
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers, method="GET" if body is None else "POST")
    attempts = 4 if body is None else 1                      # never retry a POST: it may have been accepted
    for i in range(attempts):
        try:
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            if body is not None or e.code not in (429, 500, 502, 503) or i == attempts - 1:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if i == attempts - 1:
                raise
        time.sleep(2 * (i + 1))


def get_json(url: str, key: str | None = None, timeout: float = 40):
    return request_json(url, key=key, timeout=timeout)


def post_json(url: str, body: dict, key: str | None = None, timeout: float = 60):
    return request_json(url, key=key, body=body, timeout=timeout)
