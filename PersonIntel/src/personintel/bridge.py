"""Brueckenbetrieb: zeilenweises JSON ueber stdin/stdout (NDJSON).

Damit kann ein fremdes Vorderteil - etwa die SDL2-Oberflaeche der Flipper-One-App - PersonIntel
benutzen, ohne Python einzubetten und ohne die Oberflaeche aus ``personintel.ui`` zu starten.
Der Prozess ist kurzlebig: er wird fuer eine Aufgabe gestartet und endet mit ``bye`` oder EOF.

Protokoll
---------
Eine Anfrage pro Zeile::

    {"op": "status", "id": 1}

Eine oder mehrere Antwortzeilen mit derselben ``id``. Zwischenmeldungen tragen ``event``,
die letzte Zeile einer Anfrage traegt ``ok`` (true/false)::

    {"id": 1, "event": "status", "adapter": "holehe", "state": "not_installed", ...}
    {"id": 1, "ok": true}

Auf stdout steht ausschliesslich NDJSON; Warnungen und Spuren gehen nach stderr.

Die Recherchekontrolle gilt unveraendert: ``query`` verlangt fuer aktive Pruefungen eine
Bestaetigung, die das Vorderteil beim Menschen eingeholt haben muss (Feld ``confirm``), und
laeuft durch dasselbe :class:`AuthorizationGate` wie die Oberflaeche. Die Bruecke kann die
Pruefung nicht umgehen - sie hat keinen eigenen Weg zu den Adaptern.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Optional, TextIO

from . import RESULT_SCHEMA_VERSION, __version__
from .core.config import AppPaths
from .core.engine import Engine
from .core.errors import AdapterNotAvailable, PersonIntelError
from .core.models import Evidence, FindingStatus, Purpose, QueryKind, QueryMode, QueryState, ReviewState
from .security.authorization import PURPOSE_CATEGORIES, ActiveConfirmation

PROTOCOL_VERSION = 1
DEVICE_CASE_NAME = "Geräterecherche"
MAX_LINE = 64 * 1024


class BridgeError(PersonIntelError):
    """Fehler, der als ``ok: false`` zurueckgemeldet wird (kein Absturz)."""

    def __init__(self, message: str, requirement: str = ""):
        super().__init__(message)
        self.requirement = requirement


def _b(value: Any) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "ja", "on")


class Bridge:
    def __init__(self, engine: Engine, out: TextIO):
        self.engine = engine
        self.out = out
        self._id: Any = None

    # ------------------------------------------------------------- Ausgabe
    def _write(self, obj: dict[str, Any]) -> None:
        obj = {"id": self._id, **obj}
        self.out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.out.flush()

    def event(self, name: str, /, **fields: Any) -> None:
        """Zwischenmeldung. ``name`` ist bewusst nur positionell, damit ein Feld ``name``
        oder ``kind`` in den Nutzdaten nicht mit dem Parameter kollidiert."""
        self._write({"event": name, **fields})

    # -------------------------------------------------------------- Ablauf
    def handle_line(self, line: str) -> None:
        self._id = None
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("Objekt erwartet")
        except ValueError as exc:
            self._write({"ok": False, "error": f"Ungültige Anfrage: {exc}"})
            return
        self._id = req.get("id")
        op = str(req.get("op", ""))
        fn: Optional[Callable[[dict], dict]] = getattr(self, f"op_{op.replace('.', '_')}", None)
        if fn is None:
            self._write({"ok": False, "error": f"Unbekannte Anweisung: {op or '(leer)'}"})
            return
        try:
            result = fn(req) or {}
            self._write({"ok": True, **result})
        except BridgeError as exc:
            self._write({"ok": False, "error": str(exc), "requirement": exc.requirement})
        except AdapterNotAvailable as exc:
            self._write({"ok": False, "error": str(exc), "requirement": exc.requirement})
        except PersonIntelError as exc:
            self._write({"ok": False, "error": str(exc)})
        except Exception as exc:  # nie abbrechen: das Vorderteil bleibt bedienbar
            traceback.print_exc(file=sys.stderr)
            self._write({"ok": False, "error": f"Interner Fehler ({type(exc).__name__}): {exc}"})

    def run(self, inp: TextIO) -> int:
        for raw in inp:
            line = raw.strip()
            if not line:
                continue
            if len(line) > MAX_LINE:
                self._id = None
                self._write({"ok": False, "error": "Anfrage zu lang."})
                continue
            if line == "bye" or line == '{"op":"bye"}':
                return 0
            self.handle_line(line)
            if getattr(self, "_stop", False):
                return 0
        return 0

    # ------------------------------------------------------- Anweisungen
    def op_hello(self, req: dict) -> dict:
        return {"app": "personintel", "version": __version__, "protocol": PROTOCOL_VERSION,
                "schema": RESULT_SCHEMA_VERSION, "adapters": len(self.engine.adapters()),
                "data_dir": str(self.engine.paths.data_dir),
                "encrypted": self.engine.repo.is_encrypted,
                "credentials_locked": self.engine.credentials.locked}

    def op_bye(self, req: dict) -> dict:
        self._stop = True
        return {}

    def op_status(self, req: dict) -> dict:
        """Echter Betriebsstatus aller Module - eine Zwischenmeldung je Modul."""
        statuses = {s.adapter_id: s for s in self.engine.statuses()}
        ready = 0
        for ad in self.engine.adapters():
            st = statuses.get(ad.id)
            if st is None:
                continue
            caps = ad.get_capabilities()
            available = st.state.value == "available"
            ready += 1 if available else 0
            self.event("status", adapter=ad.id, name=ad.name, category=ad.category,
                       state=st.state.value, state_label=st.state.label_de, version=st.version,
                       message=st.message, requirement=st.requirement,
                       license=st.license_status, connection=st.connection_status,
                       enabled=self.engine.settings.is_enabled(ad.id),
                       kinds=[c.kind.value for c in caps if c.available],
                       modes=sorted({c.mode.value for c in caps if c.available}),
                       needs_key=any(f.secret for f in ad.config_fields),
                       cost=any(c.cost_note for c in caps))
        return {"count": len(statuses), "ready": ready}

    # ---- Fall und Zweck ----------------------------------------------------
    def _case(self, req: dict, *, required: bool = True):
        cid = req.get("case_id")
        if cid:
            return self.engine.case(str(cid))
        cases = self.engine.cases()
        if cases:
            return cases[0]          # list_cases ist nach created_at absteigend sortiert
        if required:
            raise BridgeError("Kein Fall vorhanden.", "Zuerst einen Fall mit Zweck anlegen (case.open).")
        return None

    def op_case_info(self, req: dict) -> dict:
        case = self._case(req, required=False)
        if case is None:
            return {"case": None}
        return {"case": self._case_dict(case)}

    def _case_dict(self, case) -> dict:
        p = case.purpose
        targets = self.engine.targets(case.id)
        return {"id": case.id, "name": case.name, "created_at": case.created_at,
                "purpose_valid": self.engine.gate.purpose_valid(case),
                "purpose": None if p is None else {
                    "category": p.category, "description": p.description, "authorized_by": p.authorized_by,
                    "expires_at": p.expires_at, "active_checks_allowed": p.active_checks_allowed,
                    "allowed_kinds": list(p.allowed_kinds)},
                "targets": [{"id": t.id, "kind": t.kind.value, "value": t.value} for t in targets],
                "targets_max": self.engine.settings.limits.max_targets_per_case,
                "findings": len(self.engine.findings(case.id))}

    def op_case_open(self, req: dict) -> dict:
        """Legt einen Fall mit dokumentiertem Zweck an oder erneuert den Zweck."""
        description = str(req.get("purpose") or "").strip()
        min_chars = self.engine.settings.limits.min_purpose_chars
        if len(description) < min_chars:
            raise BridgeError(f"Der Recherchezweck muss konkret beschrieben werden "
                              f"(mindestens {min_chars} Zeichen).")
        category = str(req.get("category") or "journalism")
        if category not in PURPOSE_CATEGORIES:
            raise BridgeError(f"Unbekannte Zweckkategorie: {category}")
        authorized_by = str(req.get("authorized_by") or "").strip() or "Gerätebenutzer"
        active = _b(req.get("active", True))
        days = int(req.get("days") or 1)
        name = str(req.get("name") or "").strip() or DEVICE_CASE_NAME
        reuse = _b(req.get("reuse", True))

        case = None
        if reuse and not req.get("new"):
            for c in self.engine.cases():
                if c.name == name:
                    case = c
                    break
        if case is None:
            case = self.engine.create_case(name)
        purpose = Purpose(category=category, description=description, authorized_by=authorized_by,
                          legal_basis_note=str(req.get("legal_basis") or ""), active_checks_allowed=active)
        case = self.engine.set_purpose(case.id, purpose, days_valid=days)
        return {"case": self._case_dict(case)}

    def op_case_list(self, req: dict) -> dict:
        for c in self.engine.cases():
            self.event("case", **self._case_dict(c))
        return {}

    def op_target_add(self, req: dict) -> dict:
        case = self._case(req)
        kind = QueryKind(str(req.get("kind")))
        value = str(req.get("value") or "")
        existing = [t for t in self.engine.targets(case.id)
                    if t.kind is kind and t.value.strip().lower() == value.strip().lower()]
        if existing:
            t = existing[0]
        else:
            t = self.engine.add_target(case.id, kind, value, str(req.get("label") or ""))
        return {"target": {"id": t.id, "kind": t.kind.value, "value": t.value}, "case_id": case.id}

    # ---- Abfrage -----------------------------------------------------------
    def _confirmation(self, req: dict, value: str) -> Optional[ActiveConfirmation]:
        c = req.get("confirm")
        if not isinstance(c, dict):
            return None
        return ActiveConfirmation(typed_target=str(c.get("typed_target") or value),
                                  acknowledges_third_party_contact=_b(c.get("third_party")),
                                  acknowledges_terms_of_service=_b(c.get("tos")),
                                  note=str(c.get("note") or ""))

    def op_query(self, req: dict) -> dict:
        """Fuehrt eine Abfrage mit allen passenden (oder genannten) Modulen aus und streamt Befunde."""
        case = self._case(req)
        kind = QueryKind(str(req.get("kind")))
        value = str(req.get("value") or "")
        target = self.op_target_add({"case_id": case.id, "kind": kind.value, "value": value})["target"]
        wanted = req.get("adapters")
        if isinstance(wanted, str):
            wanted = [wanted]
        confirmation = self._confirmation(req, target["value"])
        options = req.get("options") if isinstance(req.get("options"), dict) else {}
        timeout = float(req.get("timeout") or self.engine.settings.limits.query_timeout_seconds)

        candidates = []
        for ad in self.engine.adapters():
            if wanted and ad.id not in wanted:
                continue
            cap = ad.capability(kind)
            if cap is None:
                continue
            candidates.append((ad, cap))
        if not candidates:
            raise BridgeError(f"Kein Modul unterstützt „{kind.label_de}“.")

        started, skipped, failed = [], [], []
        for ad, cap in candidates:
            if not cap.available:
                skipped.append(ad.id)
                self.event("skipped", adapter=ad.id, name=ad.name, reason=cap.reason or "nicht verfügbar",
                           requirement=getattr(ad, "missing_requirement", lambda: "")() if hasattr(
                               ad, "missing_requirement") else "")
                continue
            try:
                rec = self.engine.run_query(case.id, ad.id, target["id"], kind=kind,
                                            confirmation=confirmation if cap.mode is QueryMode.ACTIVE else None,
                                            options=options)
            except PersonIntelError as exc:
                failed.append(ad.id)
                self.event("denied", adapter=ad.id, name=ad.name, reason=str(exc))
                continue
            started.append((ad, rec))
            self.event("started", adapter=ad.id, name=ad.name, query_id=rec.id, mode=cap.mode.value,
                       cost=cap.cost_note)

        seen: set[str] = set()
        for ad, rec in started:
            try:
                done = self.engine.wait(rec.id, timeout)
            except Exception as exc:
                self.event("query", adapter=ad.id, name=ad.name, state="failed", message=str(exc))
                failed.append(ad.id)
                continue
            for f in self.engine.findings(case.id):
                if f.query_id != done.id or f.id in seen:
                    continue
                seen.add(f.id)
                src = self.engine.repo.get("source", f.source_id) if f.source_id else None
                self.event("finding", adapter=ad.id, name=ad.name, finding_id=f.id, type=f.type,
                           title=f.title, value=f.value, url=f.url, status=f.status.value,
                           evidence=f.evidence.value, evidence_label=f.evidence.label_de,
                           review=f.review_state.value, observed_at=f.observed_at, tags=list(f.tags),
                           data=f.data,
                           source=None if src is None else {
                               "description": src.description, "url": src.url, "kind": src.kind,
                               "retrieved_at": src.retrieved_at, "tool_version": src.tool_version,
                               "active": src.active})
            self.event("query", adapter=ad.id, name=ad.name, state=done.state.value,
                       message=done.message, findings=done.finding_count)
            if done.state is QueryState.FAILED:
                failed.append(ad.id)
        return {"case_id": case.id, "target": target, "started": [a.id for a, _ in started],
                "skipped": skipped, "failed": failed, "findings": len(seen)}

    def op_cancel(self, req: dict) -> dict:
        return {"cancelled": self.engine.cancel_query(str(req.get("query_id") or ""))}

    # ---- Ergebnisse --------------------------------------------------------
    def op_findings(self, req: dict) -> dict:
        case = self._case(req)
        only = str(req.get("evidence") or "")
        for f in self.engine.findings(case.id, include_rejected=_b(req.get("include_rejected", False))):
            if only and f.evidence.value != only:
                continue
            src = self.engine.repo.get("source", f.source_id) if f.source_id else None
            self.event("finding", finding_id=f.id, adapter=f.adapter_id, type=f.type, title=f.title,
                       value=f.value, url=f.url, status=f.status.value, evidence=f.evidence.value,
                       evidence_label=f.evidence.label_de, review=f.review_state.value,
                       observed_at=f.observed_at, tags=list(f.tags),
                       source=None if src is None else {"description": src.description,
                                                        "retrieved_at": src.retrieved_at,
                                                        "tool_version": src.tool_version,
                                                        "active": src.active, "url": src.url})
        return {"case_id": case.id}

    def op_review(self, req: dict) -> dict:
        ev = req.get("evidence")
        f = self.engine.review_finding(str(req.get("finding_id")), ReviewState(str(req.get("state", "reviewed"))),
                                        str(req.get("note") or ""), Evidence(ev) if ev else None)
        return {"finding_id": f.id, "evidence": f.evidence.value, "review": f.review_state.value}

    def op_graph_suggest(self, req: dict) -> dict:
        case = self._case(req)
        for s in self.engine.graph.suggest_links(case.id):
            self.event("suggestion", kind=s.kind, description=s.description,
                       finding_ids=list(s.finding_ids), evidence=s.evidence.value)
        return {}

    def op_graph_nodes(self, req: dict) -> dict:
        case = self._case(req)
        labels = {n.id: n.label for n in self.engine.graph.nodes(case.id)}
        for n in self.engine.graph.nodes(case.id):
            self.event("node", node_id=n.id, type=n.type, label=n.label, findings=list(n.finding_ids))
        for e in self.engine.graph.edges(case.id):
            self.event("edge", edge_id=e.id, source=labels.get(e.source, e.source),
                       target=labels.get(e.target, e.target), relation=e.relation,
                       evidence=e.evidence.value, evidence_label=e.evidence.label_de, note=e.note,
                       basis=list(e.basis_finding_ids))
        return {}

    def op_timeline(self, req: dict) -> dict:
        case = self._case(req)
        for e in self.engine.timeline(case.id):
            self.event("entry", ts=e.ts, kind=e.kind, summary=e.summary, evidence=e.evidence)
        return {}

    def op_report(self, req: dict) -> dict:
        case = self._case(req)
        fmt = str(req.get("format") or "md")
        rep = self.engine.build_report(case.id, mask_identifiers=_b(req.get("mask", False)))
        text = {"md": rep.to_markdown, "html": rep.to_html, "json": rep.to_json}.get(fmt)
        if text is None:
            raise BridgeError(f"Unbekanntes Berichtsformat: {fmt}")
        out = str(req.get("output") or "")
        body = text()
        if out:
            p = Path(out).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
            os.chmod(p, 0o600)
            return {"written": str(p), "bytes": len(body.encode("utf-8"))}
        for line in body.splitlines():
            self.event("line", text=line)
        return {"lines": len(body.splitlines())}

    def op_audit_verify(self, req: dict) -> dict:
        ok, bad = self.engine.audit.verify()
        return {"intact": ok, "first_bad": bad, "entries": len(self.engine.audit.entries())}

    def op_delete_case(self, req: dict) -> dict:
        case = self._case(req)
        n = self.engine.delete_case(case.id, purge_audit=_b(req.get("purge_audit", False)))
        return {"deleted_records": n}


def run_bridge(data_dir: Optional[str] = None, *, inp: Optional[TextIO] = None,
               out: Optional[TextIO] = None) -> int:
    paths = AppPaths.default()
    if data_dir:
        base = Path(data_dir).expanduser()
        paths = AppPaths(data_dir=base / "data", config_dir=base / "config")
    paths.ensure()
    engine = Engine(paths, db_passphrase=os.environ.get("PERSONINTEL_DB_PASSPHRASE") or None)
    bridge = Bridge(engine, out or sys.stdout)
    try:
        return bridge.run(inp or sys.stdin)
    finally:
        engine.close()
