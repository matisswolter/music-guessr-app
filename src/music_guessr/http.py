"""Tiny stdlib HTTP helper (keeps mobile builds free of native dependencies)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .config import USER_AGENT


class HTTPError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


def request(method: str, url: str, *, params: dict | None = None, headers: dict | None = None,
            form: dict | None = None, json_body: dict | None = None, timeout: float = 15):
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params)}"
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_body is not None:
        data = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"
    elif method in ("PUT", "POST"):
        data = b""
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise HTTPError(e.code, e.read().decode(errors="replace")) from None
    return json.loads(raw) if raw else None
