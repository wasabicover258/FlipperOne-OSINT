"""Zweck- und Berechtigungspruefung pro Recherchefall.

Jede Abfrage an einen Adapter laeuft durch :meth:`AuthorizationGate.authorize`. Das Ergebnis ist
ein signiertes :class:`AuthorizedQuery`; Adapter lehnen alles ab, was nicht von diesem Gate stammt.

Regeln (Details in docs/ARCHITECTURE.md):
1. Der Fall braucht einen dokumentierten, unverfallenen Zweck (Kategorie, Beschreibung, Verantwortliche/r).
2. Die Kennung muss als Ziel im Fall registriert sein (Fallumfang, begrenzt) und genau *eine* Kennung sein.
3. Die Kennungsart muss vom Zweck erlaubt sein.
4. Aktive Pruefungen (kontaktieren fremde Dienste) erfordern: Zweck erlaubt aktive Pruefungen,
   gesonderte Bestaetigung pro Abfrage (Kennung erneut eingeben), Tagesbudget, Mindestabstand.
5. Keine Batch-/Listen-Abfragen: eine Kennung, ein Adapter, pro Autorisierung.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..core.config import Limits
from ..core.errors import AuthorizationDenied, UnauthorizedQueryError, ValidationError
from ..core.ids import new_id, now_iso
from ..core.models import Case, Purpose, QueryKind, QueryMode, Target
from ..core.validation import normalize_target
from ..storage.repository import Repository
from .audit import AuditLog

# Prozesslokaler Schluessel: nur das Gate kann gueltige Autorisierungen ausstellen.
_PROCESS_SECRET = os.urandom(32)

PURPOSE_CATEGORIES = {
    "journalism": "Journalistische Recherche",
    "verification": "Quellen-/Identitaetsverifikation",
    "authorized_security": "Autorisierte Sicherheitsuntersuchung",
    "other": "Sonstiger dokumentierter Zweck",
}


def _sign(parts: tuple[str, ...]) -> str:
    return hmac.new(_PROCESS_SECRET, "|".join(parts).encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class AuthorizedQuery:
    query_id: str
    case_id: str
    adapter_id: str
    target_id: str
    kind: QueryKind
    value: str
    mode: QueryMode
    issued_at: str
    options: tuple = ()  # tuple von (key, value) - unveraenderlich
    signature: str = ""

    def _parts(self) -> tuple[str, ...]:
        return (self.query_id, self.case_id, self.adapter_id, self.target_id, self.kind.value, self.value,
                self.mode.value, self.issued_at, json.dumps(list(self.options), sort_keys=True))

    def verify(self) -> bool:
        return bool(self.signature) and hmac.compare_digest(self.signature, _sign(self._parts()))

    def option(self, key: str, default: Any = None) -> Any:
        return dict(self.options).get(key, default)


def require_valid(aq: object) -> AuthorizedQuery:
    """Von Adaptern am Anfang von ``execute_authorized_query`` aufzurufen."""
    if not isinstance(aq, AuthorizedQuery) or not aq.verify():
        raise UnauthorizedQueryError("Abfrage ist nicht durch die Recherchekontrolle autorisiert.")
    return aq


@dataclass
class ActiveConfirmation:
    """Gesonderte Bestaetigung einer aktiven Pruefung (pro Abfrage)."""

    typed_target: str                      # Nutzer gibt die Kennung erneut ein
    acknowledges_third_party_contact: bool = False
    acknowledges_terms_of_service: bool = False
    note: str = ""


@dataclass
class AuthorizationGate:
    repo: Repository
    audit: AuditLog
    limits: Limits = field(default_factory=Limits)

    # ---------------------------------------------------------------- Zweck
    def validate_purpose(self, purpose: Purpose) -> None:
        if purpose.category not in PURPOSE_CATEGORIES:
            raise ValidationError("Unbekannte Zweckkategorie.")
        if len((purpose.description or "").strip()) < self.limits.min_purpose_chars:
            raise ValidationError(
                f"Der Recherchezweck muss konkret beschrieben werden (mind. {self.limits.min_purpose_chars} Zeichen).")
        if not (purpose.authorized_by or "").strip():
            raise ValidationError("Verantwortliche/r bzw. Auftraggeber/in ist anzugeben.")

    def set_purpose(self, case: Case, purpose: Purpose, *, days_valid: int = 30) -> Case:
        self.validate_purpose(purpose)
        days = max(1, min(int(days_valid), self.limits.max_purpose_days))
        now = datetime.now(timezone.utc).replace(microsecond=0)
        purpose.confirmed_at = now.isoformat()
        purpose.expires_at = (now + timedelta(days=days)).isoformat()
        case.purpose = purpose
        self.repo.save_case(case)
        self.audit.record("purpose.set", case_id=case.id, detail={
            "category": purpose.category, "active_checks_allowed": purpose.active_checks_allowed,
            "expires_at": purpose.expires_at, "authorized_by": purpose.authorized_by})
        return case

    @staticmethod
    def purpose_valid(case: Case) -> bool:
        p = case.purpose
        if not p or not p.confirmed_at or not p.expires_at:
            return False
        return datetime.fromisoformat(p.expires_at) > datetime.now(timezone.utc)

    # --------------------------------------------------------------- Ziele
    def register_target(self, case: Case, kind: QueryKind | str, value: str, label: str = "") -> Target:
        kind = QueryKind(kind)
        norm = normalize_target(kind, value)
        existing = self.repo.list("target", case.id)
        if any(t.kind is kind and t.value == norm for t in existing):
            raise ValidationError("Diese Kennung ist im Fall bereits registriert.")
        if len(existing) >= self.limits.max_targets_per_case:
            raise AuthorizationDenied(
                f"Fallumfang ueberschritten (max. {self.limits.max_targets_per_case} Kennungen pro Fall). "
                "Legen Sie fuer eine weitere Person einen eigenen Fall mit eigenem Zweck an.")
        t = Target(id=new_id("tgt"), case_id=case.id, kind=kind, value=norm, label=label)
        self.repo.put("target", t, ts=t.created_at)
        self.audit.record("target.add", case_id=case.id, target_ref=self.audit.target_ref(norm),
                          detail={"kind": kind.value})
        return t

    # ------------------------------------------------------------ Freigabe
    def authorize(self, case: Case, target: Target, adapter: Any, kind: QueryKind | str,
                  confirmation: Optional[ActiveConfirmation] = None,
                  options: Optional[dict] = None) -> AuthorizedQuery:
        """Stellt eine Autorisierung aus oder wirft :class:`AuthorizationDenied`."""
        kind = QueryKind(kind)
        ref = self.audit.target_ref(target.value)

        def deny(reason: str) -> None:
            self.audit.record("query.denied", case_id=case.id, adapter_id=adapter.id, target_ref=ref,
                              detail={"reason": reason, "kind": kind.value})
            raise AuthorizationDenied(reason)

        if target.case_id != case.id:
            deny("Kennung gehoert nicht zu diesem Fall.")
        if not self.purpose_valid(case):
            deny("Kein gueltiger, dokumentierter Recherchezweck (fehlt oder abgelaufen).")
        assert case.purpose is not None
        if kind.value not in case.purpose.allowed_kinds:
            deny(f"Der Zweck erlaubt keine Abfragen vom Typ '{kind.label_de}'.")
        if target.kind is not kind:
            deny("Die Abfrageart passt nicht zur registrierten Kennung.")
        try:
            if kind is not QueryKind.REPORT_FILE and normalize_target(kind, target.value) != target.value:
                deny("Kennung ist nicht normalisiert.")
        except ValidationError as exc:
            deny(str(exc))

        cap = next((c for c in adapter.get_capabilities() if c.kind is kind), None)
        if cap is None:
            deny(f"Modul '{adapter.name}' unterstuetzt '{kind.label_de}' nicht.")
        if not cap.available:
            deny(f"Funktion nicht verfuegbar: {cap.reason or 'Voraussetzung fehlt'}")
        if not getattr(adapter, "enabled", True):
            deny(f"Modul '{adapter.name}' ist deaktiviert.")

        if cap.mode is QueryMode.ACTIVE:
            if not case.purpose.active_checks_allowed:
                deny("Der Zweck dieses Falls erlaubt keine aktiven Pruefungen (Abfragen bei Drittdiensten).")
            if confirmation is None:
                deny("Aktive Pruefung: gesonderte Bestaetigung erforderlich.")
            if (confirmation.typed_target or "").strip().lower() != target.value.lower():
                deny("Bestaetigung ungueltig: die erneut eingegebene Kennung stimmt nicht ueberein.")
            if not (confirmation.acknowledges_third_party_contact and confirmation.acknowledges_terms_of_service):
                deny("Aktive Pruefung: Hinweise zu Drittkontakt und Nutzungsbedingungen muessen bestaetigt werden.")
            since = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
            if self.repo.count_active_queries(case.id, since) >= self.limits.max_active_queries_per_case_per_day:
                deny("Tagesbudget fuer aktive Pruefungen in diesem Fall ausgeschoepft.")
            last = self.repo.last_active_query_ts(case.id, adapter.id)
            if last:
                delta = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
                if delta < self.limits.min_active_interval_seconds:
                    deny(f"Mindestabstand zwischen aktiven Abfragen ({self.limits.min_active_interval_seconds:.0f} s) "
                         "noch nicht erreicht.")

        opts = tuple(sorted((options or {}).items()))
        aq = AuthorizedQuery(query_id=new_id("qry"), case_id=case.id, adapter_id=adapter.id, target_id=target.id,
                             kind=kind, value=target.value, mode=cap.mode, issued_at=now_iso(), options=opts)
        aq = AuthorizedQuery(**{**aq.__dict__, "signature": _sign(aq._parts())})
        self.audit.record("query.authorized", case_id=case.id, adapter_id=adapter.id, target_ref=ref, detail={
            "kind": kind.value, "mode": cap.mode.value, "query_id": aq.query_id,
            "confirmation_note": (confirmation.note if confirmation else "")})
        return aq
