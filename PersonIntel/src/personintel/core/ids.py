"""Eindeutige, praefixierte Kennungen (Faelle, Quellen, Befunde ...)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

_ID_RE = re.compile(r"^[a-z]{2,8}_[0-9a-f]{16}$")


def new_id(prefix: str) -> str:
    """Erzeugt z. B. ``case_3f9a...`` - global eindeutig genug fuer Export/Import."""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def is_valid_id(value: str, prefix: str | None = None) -> bool:
    if not isinstance(value, str) or not _ID_RE.match(value):
        return False
    return prefix is None or value.startswith(prefix + "_")


def now_iso() -> str:
    """UTC-Zeitstempel (Sekunden), ISO 8601."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
