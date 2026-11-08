"""Hilfen zum Erzeugen von Quellen und Befunden in Adaptern."""

from __future__ import annotations

import re
from typing import Any

from ..core.ids import new_id
from ..core.models import Evidence, Finding, FindingStatus, Source
from .base import RawResult

_SECRET_KEY = re.compile(r"(pass(word|wd)?|pwd|secret|credential|hash|token|api[_-]?key|salt)", re.I)


def make_source(raw: RawResult, description: str, *, kind: str = "tool_output", url: str = "",
                active: bool = False) -> Source:
    return Source(id=new_id("src"), case_id=raw.case_id, adapter_id=raw.adapter_id, kind=kind,
                  description=description, url=url, retrieved_at=raw.finished_at, query_id=raw.query_id,
                  tool_version=raw.tool_version, active=active)


def make_finding(raw: RawResult, source: Source, type_: str, title: str, *, value: str = "", url: str = "",
                 status: FindingStatus = FindingStatus.INFO, evidence: Evidence = Evidence.UNCONFIRMED,
                 data: dict[str, Any] | None = None, tags: list[str] | None = None) -> Finding:
    return Finding(id=new_id("fnd"), case_id=raw.case_id, adapter_id=raw.adapter_id, type=type_, title=title,
                   value=value, url=url, status=status, evidence=evidence, observed_at=raw.finished_at,
                   query_id=raw.query_id, source_id=source.id, target_id=raw.target_id, data=data or {},
                   tags=tags or [])


def strip_secret_keys(obj: Any) -> Any:
    """Entfernt rekursiv alle Schluessel, die nach Passwort/Hash/Token/Geheimnis aussehen."""
    if isinstance(obj, dict):
        return {k: strip_secret_keys(v) for k, v in obj.items() if not _SECRET_KEY.search(str(k))}
    if isinstance(obj, list):
        return [strip_secret_keys(v) for v in obj]
    return obj


def truthy(v: Any) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "y")
