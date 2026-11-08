"""Minimaler HTTP-Client (nur Standardbibliothek) fuer Anbieter-APIs und lokale REST-Schnittstellen."""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

from ..core.errors import AdapterError

USER_AGENT = "PersonIntel/0.1 (+local desktop research tool)"
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def safe_base_url(candidate: str, default: str) -> str:
    """Erlaubt eine abweichende Basis-URL nur per HTTPS oder auf Loopback (Tests, lokale Gateways)."""
    candidate = (candidate or "").strip().rstrip("/")
    if not candidate:
        return default
    u = urlparse(candidate)
    if u.scheme == "https" and u.hostname:
        return candidate
    if u.scheme == "http" and u.hostname in _LOOPBACK:
        return candidate
    raise AdapterError("Basis-URL muss HTTPS verwenden (oder http auf localhost).")


@dataclass
class HttpResponse:
    status: int
    json: Any
    text: str


def redact(text: str, *secrets: Optional[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return re.sub(r"(key=)[^&\s]+", r"\1***", text)


def request(method: str, url: str, *, headers: Optional[Mapping[str, str]] = None,
            params: Optional[Mapping[str, str]] = None, form: Optional[Mapping[str, str]] = None,
            timeout: float = 30.0, secrets: tuple[Optional[str], ...] = ()) -> HttpResponse:
    """Fuehrt eine Anfrage aus und liefert auch Fehlerantworten (4xx/5xx) als Response zurueck."""
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = urllib.parse.urlencode(form).encode("utf-8") if form is not None else None
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if form is not None:
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:  # noqa: S310 (Schema geprueft)
            body = resp.read(8_000_000).decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read(1_000_000).decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AdapterError(redact(f"Verbindungsfehler: {exc}", *secrets)) from exc
    try:
        parsed = json.loads(body) if body else None
    except ValueError:
        parsed = None
    return HttpResponse(status=status, json=parsed, text=body)
