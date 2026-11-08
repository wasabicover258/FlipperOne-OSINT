"""Gemeinsame Datenmodelle und das versionierte Ergebnisformat.

Alle Modelle sind einfache Dataclasses mit ``to_dict``/``from_dict``. Das JSON-
Format wird durch ``RESULT_SCHEMA_VERSION`` versioniert (siehe docs/FUSION.md).
"""

from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional

from .ids import now_iso


class Evidence(str, enum.Enum):
    """Belegstufe eines Befunds (UI-Pflicht: immer sichtbar)."""

    CONFIRMED = "confirmed"      # unmittelbar belegt
    INDICATION = "indication"    # nur ein Indiz
    UNCONFIRMED = "unconfirmed"  # noch unbestaetigt

    @property
    def label_de(self) -> str:
        return {"confirmed": "unmittelbar belegt", "indication": "Indiz",
                "unconfirmed": "unbestätigt"}[self.value]

    @property
    def rank(self) -> int:
        return {"unconfirmed": 0, "indication": 1, "confirmed": 2}[self.value]


class QueryKind(str, enum.Enum):
    EMAIL = "email"
    USERNAME = "username"
    PHONE = "phone"
    NAME = "name"
    REPORT_FILE = "report_file"   # lokaler Import (z. B. Mr.Holmes-Bericht)

    @property
    def label_de(self) -> str:
        return {"email": "E-Mail", "username": "Benutzername", "phone": "Telefonnummer",
                "name": "Name", "report_file": "Berichtsdatei"}[self.value]


class QueryMode(str, enum.Enum):
    PASSIVE = "passive"  # nur lokale Verarbeitung / keine Kontaktaufnahme mit Dritten
    ACTIVE = "active"    # kontaktiert fremde Dienste -> gesonderte Bestaetigung


class FindingStatus(str, enum.Enum):
    FOUND = "found"          # vom Tool/Dienst gemeldeter Treffer
    POSSIBLE = "possible"    # moegliche Zuordnung (bekannt unzuverlaessiges Modul etc.)
    NOT_FOUND = "not_found"
    FAILED = "failed"        # Abfrage fehlgeschlagen (Rate-Limit, Timeout, Fehler)
    INFO = "info"            # Metadaten / Zusammenfassung


class ReviewState(str, enum.Enum):
    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class QueryState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _coerce_value(tp: Any, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(tp, type) and issubclass(tp, enum.Enum):
        return tp(value)
    return value


class Model:
    """Mixin fuer (De-)Serialisierung."""

    ENUM_FIELDS: ClassVar[dict[str, type]] = {}
    NESTED: ClassVar[dict[str, type]] = {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            v = getattr(self, f.name)
            if isinstance(v, enum.Enum):
                v = v.value
            elif isinstance(v, Model):
                v = v.to_dict()
            elif isinstance(v, list):
                v = [x.to_dict() if isinstance(x, Model) else (x.value if isinstance(x, enum.Enum) else x) for x in v]
            out[f.name] = v
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        names = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
        kwargs: dict[str, Any] = {}
        for k, v in data.items():
            if k not in names:
                continue  # Vorwaertskompatibilitaet: unbekannte Felder ignorieren
            if k in cls.ENUM_FIELDS:
                v = _coerce_value(cls.ENUM_FIELDS[k], v)
            elif k in cls.NESTED and isinstance(v, dict):
                v = cls.NESTED[k].from_dict(v)
            kwargs[k] = v
        return cls(**kwargs)


@dataclass
class Purpose(Model):
    """Dokumentierte Zweck- und Berechtigungspruefung eines Recherchefalls."""

    category: str = ""            # journalism | verification | authorized_security | other
    description: str = ""         # Pflicht: konkreter Recherchezweck (>= 20 Zeichen)
    authorized_by: str = ""       # wer verantwortet/genehmigt die Recherche
    legal_basis_note: str = ""    # Notiz zur Rechtsgrundlage / Auftrag
    confirmed_at: str = ""
    expires_at: str = ""          # Zweckbindung ist befristet
    active_checks_allowed: bool = False
    allowed_kinds: list = field(default_factory=lambda: ["email", "username", "phone", "name", "report_file"])


@dataclass
class Case(Model):
    id: str
    name: str
    description: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    purpose: Optional[Purpose] = None
    origin: str = "personintel"
    schema_version: str = "1.0"

    NESTED: ClassVar[dict[str, type]] = {"purpose": Purpose}


@dataclass
class Target(Model):
    """Eine registrierte Kennung (E-Mail, Benutzername ...) im Fallumfang."""

    id: str
    case_id: str
    kind: QueryKind
    value: str
    label: str = ""
    created_at: str = field(default_factory=now_iso)

    ENUM_FIELDS: ClassVar[dict[str, type]] = {"kind": QueryKind}


@dataclass
class Source(Model):
    """Herkunftsnachweis: Welches Tool/Welcher Dienst hat wann geliefert?"""

    id: str
    case_id: str
    adapter_id: str
    kind: str = "tool_output"     # tool_output | api | file
    description: str = ""
    url: str = ""
    retrieved_at: str = field(default_factory=now_iso)
    query_id: str = ""
    tool_version: str = ""
    active: bool = False


@dataclass
class Finding(Model):
    id: str
    case_id: str
    adapter_id: str
    type: str                      # account | profile | person_record | metadata | breach_hint | summary | document | link_hint
    title: str
    value: str = ""
    url: str = ""
    status: FindingStatus = FindingStatus.INFO
    evidence: Evidence = Evidence.UNCONFIRMED
    review_state: ReviewState = ReviewState.UNREVIEWED
    reviewer_note: str = ""
    reviewed_at: str = ""
    observed_at: str = field(default_factory=now_iso)
    query_id: str = ""
    source_id: str = ""
    target_id: str = ""
    data: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)

    ENUM_FIELDS: ClassVar[dict[str, type]] = {
        "status": FindingStatus, "evidence": Evidence, "review_state": ReviewState}


@dataclass
class QueryRecord(Model):
    id: str
    case_id: str
    adapter_id: str
    target_id: str
    kind: QueryKind
    mode: QueryMode
    state: QueryState = QueryState.QUEUED
    started_at: str = ""
    finished_at: str = ""
    message: str = ""
    finding_count: int = 0
    created_at: str = field(default_factory=now_iso)

    ENUM_FIELDS: ClassVar[dict[str, type]] = {
        "kind": QueryKind, "mode": QueryMode, "state": QueryState}


@dataclass
class Event(Model):
    """Eintrag der chronologischen Ansicht."""

    id: str
    case_id: str
    type: str
    summary: str
    ts: str = field(default_factory=now_iso)
    ref_id: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class NormalizedBatch:
    """Ergebnis von ``Adapter.normalize_results``."""

    findings: list[Finding] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
