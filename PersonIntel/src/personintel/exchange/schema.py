"""Versioniertes JSON-Austauschformat fuer Faelle (Export/Import, Fusion).

Aufbau eines Bundles (``format = "personintel.case"``, ``schema_version = "1.0"``)::

    {
      "format": "personintel.case", "schema_version": "1.0", "exported_at": "...",
      "origin": {"app": "personintel", "version": "0.1.0"},
      "case": {...}, "targets": [...], "sources": [...], "findings": [...],
      "queries": [...], "events": [...], "graph": {"nodes": [...], "edges": [...]}
    }

Regeln: gleiche Hauptversion -> importierbar; unbekannte Felder werden ignoriert
(Vorwaertskompatibilitaet); alle IDs sind praefixiert und global eindeutig; beim Import in eine
Datenbank, in der die IDs bereits existieren, werden alle IDs konsistent neu vergeben.
Das Audit-Protokoll wird nicht exportiert (lokal und fallunabhaengig).
"""

from __future__ import annotations

from typing import Any

from .. import EXCHANGE_FORMAT, RESULT_SCHEMA_VERSION, __version__
from ..core.errors import ExchangeError
from ..core.ids import is_valid_id, new_id, now_iso
from ..core.models import Case, Event, Finding, QueryRecord, Source, Target
from ..graph.model import GraphEdge, GraphNode
from ..storage.repository import Repository

MAX_RECORDS = 200_000
_SECTIONS: dict[str, Any] = {"targets": Target, "sources": Source, "findings": Finding,
                             "queries": QueryRecord, "events": Event}
_KIND = {"targets": "target", "sources": "source", "findings": "finding", "queries": "query", "events": "event"}


def _major(version: str) -> int:
    try:
        return int(str(version).split(".")[0])
    except (ValueError, IndexError):
        raise ExchangeError(f"Ungültige Schemaversion: {version!r}") from None


def export_case(repo: Repository, case_id: str, *, include_graph: bool = True) -> dict[str, Any]:
    case = repo.get_case(case_id)
    if case is None:
        raise ExchangeError("Fall nicht gefunden.")
    bundle: dict[str, Any] = {
        "format": EXCHANGE_FORMAT,
        "schema_version": RESULT_SCHEMA_VERSION,
        "exported_at": now_iso(),
        "origin": {"app": "personintel", "version": __version__},
        "case": case.to_dict(),
    }
    for section, kind in _KIND.items():
        bundle[section] = [r.to_dict() for r in repo.list(kind, case_id)]
    if include_graph:
        bundle["graph"] = {"nodes": repo.list_raw("node", case_id), "edges": repo.list_raw("edge", case_id)}
    return bundle


def validate_bundle(data: Any) -> None:
    """Strukturpruefung; wirft :class:`ExchangeError` mit verstaendlicher Meldung."""
    if not isinstance(data, dict):
        raise ExchangeError("Kein gültiges Fall-Bundle (JSON-Objekt erwartet).")
    if data.get("format") != EXCHANGE_FORMAT:
        raise ExchangeError(f"Unbekanntes Format: {data.get('format')!r} (erwartet {EXCHANGE_FORMAT!r}).")
    if _major(data.get("schema_version", "")) != _major(RESULT_SCHEMA_VERSION):
        raise ExchangeError(
            f"Inkompatible Schemaversion {data.get('schema_version')!r}; unterstützt wird Hauptversion "
            f"{_major(RESULT_SCHEMA_VERSION)}.x.")
    case = data.get("case")
    if not isinstance(case, dict) or not is_valid_id(case.get("id", ""), "case"):
        raise ExchangeError("Fall-ID fehlt oder ist ungültig.")
    total = 0
    seen: set[str] = {case["id"]}
    for section, cls in _SECTIONS.items():
        items = data.get(section, [])
        if not isinstance(items, list):
            raise ExchangeError(f"Abschnitt '{section}' muss eine Liste sein.")
        total += len(items)
        for it in items:
            _check_record(section, it, case["id"], seen)
            try:
                cls.from_dict(it)
            except (ValueError, TypeError, KeyError) as exc:
                raise ExchangeError(f"Ungültiger Datensatz in '{section}': {exc}") from exc
    graph = data.get("graph") or {}
    for section, cls in (("nodes", GraphNode), ("edges", GraphEdge)):
        items = graph.get(section, [])
        if not isinstance(items, list):
            raise ExchangeError(f"graph.{section} muss eine Liste sein.")
        total += len(items)
        for it in items:
            _check_record(f"graph.{section}", it, case["id"], seen)
            try:
                cls.from_dict(it)
            except (ValueError, TypeError, KeyError) as exc:
                raise ExchangeError(f"Ungültiger Datensatz in 'graph.{section}': {exc}") from exc
    if total > MAX_RECORDS:
        raise ExchangeError("Bundle enthält zu viele Datensätze.")
    try:
        Case.from_dict(case)
    except (ValueError, TypeError, KeyError) as exc:
        raise ExchangeError(f"Ungültiger Fall: {exc}") from exc


def _check_record(section: str, it: Any, case_id: str, seen: set[str]) -> None:
    if not isinstance(it, dict):
        raise ExchangeError(f"Ungültiger Eintrag in '{section}'.")
    rid = it.get("id", "")
    if not is_valid_id(rid):
        raise ExchangeError(f"Ungültige ID in '{section}': {rid!r}")
    if rid in seen:
        raise ExchangeError(f"Doppelte ID im Bundle: {rid}")
    seen.add(rid)
    if it.get("case_id") != case_id:
        raise ExchangeError(f"Datensatz {rid} gehört nicht zum Fall des Bundles.")


def _remap(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_remap(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: _remap(v, mapping) for k, v in value.items()}
    return value


def import_case(repo: Repository, data: dict[str, Any], *, force_new_ids: bool = False) -> Case:
    """Importiert ein Bundle. Existiert die Fall-ID bereits (oder ``force_new_ids``), werden alle IDs neu vergeben."""
    validate_bundle(data)
    case_d = data["case"]
    graph = data.get("graph") or {}
    all_ids = [case_d["id"]]
    for section in _SECTIONS:
        all_ids += [r["id"] for r in data.get(section, [])]
    for section in ("nodes", "edges"):
        all_ids += [r["id"] for r in graph.get(section, [])]
    clash = repo.case_exists(case_d["id"]) or any(repo.get_raw(i) is not None for i in all_ids[1:])
    mapping: dict[str, str] = {}
    if clash or force_new_ids:
        for old in all_ids:
            mapping[old] = new_id(old.split("_", 1)[0])
    case = Case.from_dict(_remap(case_d, mapping))
    if mapping:
        case.name = f"{case.name} (Import)"
    repo.save_case(case)
    for section, kind in _KIND.items():
        for rec in data.get(section, []):
            obj = _SECTIONS[section].from_dict(_remap(rec, mapping))
            obj.case_id = case.id
            repo.put(kind, obj, ts=getattr(obj, "ts", "") or getattr(obj, "retrieved_at", "")
                     or getattr(obj, "observed_at", "") or getattr(obj, "created_at", ""))
    for section, kind in (("nodes", "node"), ("edges", "edge")):
        for rec in graph.get(section, []):
            rec = _remap(rec, mapping)
            rec["case_id"] = case.id
            repo.put_raw(kind, rec)
    return case
