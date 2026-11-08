"""Engine: die zentrale, UI-unabhaengige Fassade von PersonIntel.

Die Oberflaeche (``personintel.ui``), das CLI und eine spaetere Hauptanwendung verwenden
ausschliesslich diese Klasse (Re-Export als ``personintel.api.PersonIntel``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..adapters.base import Adapter, AdapterStatus
from ..graph.model import GraphService
from ..security.audit import AuditLog
from ..security.authorization import ActiveConfirmation, AuthorizationGate
from ..security.credentials import CredentialStore, EncryptedFileBackend, KeyringBackend
from ..storage.repository import Repository
from .config import AppPaths, Settings
from .errors import PersonIntelError, ValidationError
from .ids import new_id, now_iso
from .jobs import JobManager
from .models import (Case, Event, Evidence, Finding, FindingStatus, Purpose, QueryKind, QueryRecord, ReviewState,
                     Source, Target)
from .plugins import PluginRegistry


@dataclass
class TimelineEntry:
    ts: str
    kind: str          # event | finding
    summary: str
    evidence: str = ""
    ref_id: str = ""


class Engine:
    def __init__(self, paths: Optional[AppPaths] = None, *, db_passphrase: Optional[str] = None,
                 registry: Optional[PluginRegistry] = None, settings: Optional[Settings] = None,
                 load_plugins: bool = False, repo: Optional[Repository] = None,
                 credential_store: Optional[CredentialStore] = None, max_workers: int = 3):
        self.paths = paths or AppPaths.default()
        self.paths.ensure()
        self.settings = settings or Settings.load(self.paths.settings_path)
        self.repo = repo or Repository(self.paths.db_path, db_passphrase)
        self.audit = AuditLog(self.repo)
        self.gate = AuthorizationGate(self.repo, self.audit, self.settings.limits)
        self.graph = GraphService(self.repo, self.audit)
        self.jobs = JobManager(self.repo, self.audit, max_workers=max_workers)
        if credential_store is not None:
            self.credentials = credential_store
        elif self.settings.credential_backend == "keyring":
            self.credentials = CredentialStore(KeyringBackend())
        else:
            self.credentials = CredentialStore(EncryptedFileBackend(self.paths.credentials_path))
        self.registry = registry or PluginRegistry()
        self.registry.load_builtin()
        self.plugin_problems: list[str] = self.registry.load_entry_points() if load_plugins else []
        self._adapters: dict[str, Adapter] = {}
        self._build_adapters()

    # ----------------------------------------------------------- Adapter
    def _build_adapters(self) -> None:
        self._adapters = {}
        for cls in self.registry.adapter_classes():
            ad = cls()
            ad.bind(self.settings.adapter_config.get(cls.id, {}), self.credentials.view(cls.id),
                    self.settings.is_enabled(cls.id))
            self._adapters[cls.id] = ad

    def adapters(self) -> list[Adapter]:
        return list(self._adapters.values())

    def adapter(self, adapter_id: str) -> Adapter:
        try:
            return self._adapters[adapter_id]
        except KeyError:
            raise PersonIntelError(f"Unbekanntes Modul: {adapter_id}") from None

    def register_adapter(self, cls, *, replace: bool = False) -> None:
        """Registriert zur Laufzeit ein weiteres Modul (Fusion/Plugins)."""
        self.registry.register_adapter(cls, replace=replace)
        ad = cls()
        ad.bind(self.settings.adapter_config.get(cls.id, {}), self.credentials.view(cls.id),
                self.settings.is_enabled(cls.id))
        self._adapters[cls.id] = ad

    def statuses(self) -> list[AdapterStatus]:
        return [a.get_status() for a in self.adapters()]

    def unlock_credentials(self, passphrase: str) -> None:
        backend = self.credentials.backend
        if isinstance(backend, EncryptedFileBackend):
            backend.unlock(passphrase)
            self.audit.record("credentials.unlock")

    def configure_adapter(self, adapter_id: str, *, config: Optional[dict[str, Any]] = None,
                          secrets: Optional[dict[str, str]] = None, enabled: Optional[bool] = None,
                          clear_secrets: Optional[list[str]] = None) -> AdapterStatus:
        """Speichert nicht-geheime Werte in den Einstellungen, Geheimnisse im Credential-Store."""
        ad = self.adapter(adapter_id)
        secret_keys = {f.key for f in ad.config_fields if f.secret}
        if config:
            clean = {k: v for k, v in config.items() if k not in secret_keys}
            self.settings.adapter_config.setdefault(adapter_id, {}).update(clean)
        for key, value in (secrets or {}).items():
            if key not in secret_keys:
                raise ValidationError(f"'{key}' ist kein geheimes Feld von {ad.name}.")
            if value:
                self.credentials.set(adapter_id, key, value)
        for key in clear_secrets or []:
            self.credentials.delete(adapter_id, key)
        if enabled is not None:
            self.settings.enabled_adapters[adapter_id] = bool(enabled)
        self.settings.save(self.paths.settings_path)
        ad.bind(self.settings.adapter_config.get(adapter_id, {}), self.credentials.view(adapter_id),
                self.settings.is_enabled(adapter_id))
        self.audit.record("adapter.configure", adapter_id=adapter_id, detail={
            "enabled": self.settings.is_enabled(adapter_id), "secret_fields_changed": len(secrets or {})})
        return ad.get_status()

    # -------------------------------------------------------------- Faelle
    def create_case(self, name: str, description: str = "") -> Case:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Der Fall braucht einen Namen.")
        case = Case(id=new_id("case"), name=name, description=description.strip())
        self.repo.save_case(case)
        self.audit.record("case.create", case_id=case.id)
        self._event(case.id, "case.created", "Fall angelegt")
        return case

    def cases(self) -> list[Case]:
        return self.repo.list_cases()

    def case(self, case_id: str) -> Case:
        c = self.repo.get_case(case_id)
        if c is None:
            raise PersonIntelError("Fall nicht gefunden.")
        return c

    def set_purpose(self, case_id: str, purpose: Purpose, days_valid: int = 30) -> Case:
        case = self.gate.set_purpose(self.case(case_id), purpose, days_valid=days_valid)
        self._event(case_id, "purpose.set", f"Zweck dokumentiert (Kategorie: {purpose.category}, "
                    f"aktive Prüfungen {'erlaubt' if purpose.active_checks_allowed else 'nicht erlaubt'})")
        return case

    def delete_case(self, case_id: str, *, purge_audit: bool = False) -> int:
        self.case(case_id)
        n = self.repo.delete_case(case_id, purge_audit=purge_audit)
        self.audit.record("case.delete", detail={"records": n, "purge_audit": purge_audit})
        if purge_audit:
            self.audit.rechain()
        return n

    # --------------------------------------------------------------- Ziele
    def add_target(self, case_id: str, kind: QueryKind | str, value: str, label: str = "") -> Target:
        t = self.gate.register_target(self.case(case_id), kind, value, label)
        self._event(case_id, "target.added", f"Kennung registriert ({QueryKind(kind).label_de})", ref_id=t.id)
        return t

    def targets(self, case_id: str) -> list[Target]:
        return self.repo.list("target", case_id)

    def remove_target(self, case_id: str, target_id: str, *, delete_data: bool = True) -> int:
        """Entfernt eine Kennung; optional samt aller Befunde/Abfragen, die zu ihr gehoeren (selektives Loeschen)."""
        ids = [target_id]
        if delete_data:
            ids += [f.id for f in self.findings(case_id) if f.target_id == target_id]
            ids += [q.id for q in self.queries(case_id) if q.target_id == target_id]
        self.repo.delete_records(ids)
        self.audit.record("target.remove", case_id=case_id, detail={"records": len(ids), "data_deleted": delete_data})
        return len(ids)

    # ------------------------------------------------------------- Abfragen
    def run_query(self, case_id: str, adapter_id: str, target_id: str, kind: Optional[QueryKind | str] = None,
                  confirmation: Optional[ActiveConfirmation] = None,
                  options: Optional[dict] = None) -> QueryRecord:
        case = self.case(case_id)
        target = self.repo.get("target", target_id)
        if target is None or target.case_id != case_id:
            raise ValidationError("Kennung nicht im Fall gefunden.")
        adapter = self.adapter(adapter_id)
        aq = self.gate.authorize(case, target, adapter, kind or target.kind, confirmation, options)
        return self.jobs.submit(aq, adapter)

    def cancel_query(self, query_id: str) -> bool:
        return self.jobs.cancel(query_id)

    def wait(self, query_id: str, timeout: Optional[float] = None) -> QueryRecord:
        return self.jobs.wait(query_id, timeout)

    def queries(self, case_id: str) -> list[QueryRecord]:
        return self.repo.list("query", case_id)

    # ------------------------------------------------------ Ergebnisse
    def findings(self, case_id: str, *, include_rejected: bool = True) -> list[Finding]:
        out = self.repo.list("finding", case_id)
        if not include_rejected:
            out = [f for f in out if f.review_state is not ReviewState.REJECTED]
        return out

    def sources(self, case_id: str) -> list[Source]:
        return self.repo.list("source", case_id)

    def review_finding(self, finding_id: str, state: ReviewState | str, note: str = "",
                       evidence: Optional[Evidence | str] = None) -> Finding:
        f = self.repo.get("finding", finding_id)
        if f is None:
            raise PersonIntelError("Befund nicht gefunden.")
        f.review_state = ReviewState(state)
        f.reviewer_note = note.strip()
        f.reviewed_at = now_iso()
        if evidence is not None:
            new = Evidence(evidence)
            if new is Evidence.CONFIRMED and not f.reviewer_note:
                raise ValidationError("Für 'unmittelbar belegt' ist eine Begründung (Notiz) nötig.")
            f.evidence = new
        self.repo.put("finding", f, ts=f.observed_at)
        self.audit.record("finding.review", case_id=f.case_id, adapter_id=f.adapter_id,
                          detail={"state": f.review_state.value, "evidence": f.evidence.value})
        self._event(f.case_id, "finding.reviewed", f"Befund geprüft: {f.review_state.value} / {f.evidence.label_de}",
                    ref_id=f.id)
        return f

    def delete_finding(self, finding_id: str) -> None:
        f = self.repo.get("finding", finding_id)
        if f is None:
            return
        self.repo.delete_record(finding_id)
        self.audit.record("finding.delete", case_id=f.case_id, adapter_id=f.adapter_id)

    def delete_query_data(self, case_id: str, query_id: str) -> int:
        """Loescht eine Abfrage samt ihrer Befunde und Quellen."""
        ids = [query_id] + [f.id for f in self.findings(case_id) if f.query_id == query_id]
        ids += [s.id for s in self.sources(case_id) if s.query_id == query_id]
        self.repo.delete_records(ids)
        self.audit.record("query.delete_data", case_id=case_id, detail={"records": len(ids)})
        return len(ids)

    # ---------------------------------------------------------- Zeitleiste
    def _event(self, case_id: str, type_: str, summary: str, ref_id: str = "") -> Event:
        ev = Event(id=new_id("evt"), case_id=case_id, type=type_, summary=summary, ref_id=ref_id)
        self.repo.put("event", ev, ts=ev.ts)
        return ev

    def timeline(self, case_id: str) -> list[TimelineEntry]:
        entries = [TimelineEntry(e.ts, "event", e.summary, ref_id=e.ref_id) for e in self.repo.list("event", case_id)]
        for f in self.findings(case_id, include_rejected=False):
            if f.status in (FindingStatus.FOUND, FindingStatus.POSSIBLE):
                entries.append(TimelineEntry(f.observed_at, "finding", f"{f.title} ({f.adapter_id})",
                                             evidence=f.evidence.label_de, ref_id=f.id))
        return sorted(entries, key=lambda e: (e.ts, e.kind))

    # ----------------------------------------------------- Austausch/Berichte
    def export_case(self, case_id: str, *, include_graph: bool = True) -> dict[str, Any]:
        from ..exchange.schema import export_case
        data = export_case(self.repo, case_id, include_graph=include_graph)
        self.audit.record("case.export", case_id=case_id)
        return data

    def import_case(self, bundle: dict[str, Any]) -> Case:
        from ..exchange.schema import import_case
        case = import_case(self.repo, bundle)
        self.audit.record("case.import", case_id=case.id)
        self._event(case.id, "case.imported", "Fall importiert")
        return case

    def build_report(self, case_id: str, **options):
        from ..reports.export import ReportOptions, build_report
        rep = build_report(self, case_id, ReportOptions(**options))
        self.audit.record("report.build", case_id=case_id)
        return rep

    # -------------------------------------------------------------- Ende
    def close(self) -> None:
        self.jobs.shutdown(wait=True)
        self.repo.close()
