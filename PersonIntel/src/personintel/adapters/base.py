"""Gemeinsame Adapter-Schnittstelle.

Jeder der zehn Connectoren implementiert :class:`Adapter`. Die Schnittstelle ist bewusst
klein und stabil (Teil der Fusions-API, siehe docs/FUSION.md).
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional, Protocol

from ..core.errors import AdapterNotAvailable
from ..core.ids import now_iso
from ..core.models import NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery, require_valid


class AdapterState(str, enum.Enum):
    AVAILABLE = "available"                 # betriebsbereit
    NOT_INSTALLED = "not_installed"         # lokales Tool nicht gefunden
    NOT_CONFIGURED = "not_configured"       # Konfiguration/Zugangsdaten fehlen
    UNVERIFIED = "unverified"               # konfiguriert, aber Zugang nicht verifizierbar/verifiziert
    UNAVAILABLE_VENDOR = "unavailable_vendor"  # Funktion ohne Anbieterfreigabe/Doku nicht verfuegbar
    DISABLED = "disabled"
    ERROR = "error"

    @property
    def label_de(self) -> str:
        return {
            "available": "Bereit", "not_installed": "Nicht installiert", "not_configured": "Nicht konfiguriert",
            "unverified": "Konfiguriert (nicht verifiziert)", "unavailable_vendor": "Nicht verfügbar (Anbieterzugang)",
            "disabled": "Deaktiviert", "error": "Fehler",
        }[self.value]


@dataclass
class ConfigField:
    key: str
    label: str
    secret: bool = False
    required: bool = False
    help: str = ""
    default: str = ""


@dataclass
class ConfigValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class InstallInfo:
    installed: bool
    path: str = ""
    version: str = ""
    message: str = ""


@dataclass
class Capability:
    kind: QueryKind
    mode: QueryMode
    label: str
    description: str = ""
    available: bool = True
    reason: str = ""          # Warum nicht verfuegbar / konkrete Voraussetzung
    cost_note: str = ""       # z. B. "kostenpflichtige Abfrage"


@dataclass
class AdapterStatus:
    adapter_id: str
    state: AdapterState
    message: str = ""
    requirement: str = ""     # konkrete Voraussetzung, falls nicht betriebsbereit
    version: str = ""
    license_status: str = "n/a"
    connection_status: str = "n/a"
    checked_at: str = field(default_factory=now_iso)


@dataclass
class RawResult:
    """Rohdaten einer Abfrage (nur im Speicher; es werden nur normalisierte Befunde gespeichert)."""

    query_id: str
    case_id: str
    target_id: str
    adapter_id: str
    started_at: str
    finished_at: str
    payload: dict[str, Any] = field(default_factory=dict)
    tool_version: str = ""
    errors: list[str] = field(default_factory=list)


class SecretReader(Protocol):
    def get(self, field: str) -> Optional[str]: ...
    def has(self, field: str) -> bool: ...


class _NoSecrets:
    def get(self, field: str) -> Optional[str]:
        return None

    def has(self, field: str) -> bool:
        return False


class Adapter(ABC):
    """Basisklasse aller Connectoren."""

    id: ClassVar[str] = ""
    name: ClassVar[str] = ""
    category: ClassVar[str] = ""
    description: ClassVar[str] = ""
    homepage: ClassVar[str] = ""
    config_fields: ClassVar[tuple[ConfigField, ...]] = ()

    def __init__(self, config: Optional[dict[str, Any]] = None, secrets: Optional[SecretReader] = None):
        self.config: dict[str, Any] = dict(config or {})
        self.secrets: SecretReader = secrets or _NoSecrets()
        self.enabled: bool = True

    def bind(self, config: dict[str, Any], secrets: SecretReader, enabled: bool = True) -> None:
        self.config = dict(config)
        self.secrets = secrets
        self.enabled = enabled

    # ---- Pflicht-Schnittstelle (laut Auftrag) -----------------------------
    @abstractmethod
    def detect_installation(self) -> InstallInfo: ...

    @abstractmethod
    def get_capabilities(self) -> list[Capability]: ...

    @abstractmethod
    def validate_configuration(self, config: Optional[dict[str, Any]] = None) -> ConfigValidation: ...

    @abstractmethod
    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult: ...

    def cancel_query(self, query_id: str) -> bool:
        """Bricht eine laufende Abfrage ab. Standard: nichts abzubrechen."""
        return False

    @abstractmethod
    def normalize_results(self, raw: RawResult) -> NormalizedBatch: ...

    def get_status(self) -> AdapterStatus:
        if not self.enabled:
            return AdapterStatus(self.id, AdapterState.DISABLED, "Modul ist deaktiviert.")
        try:
            install = self.detect_installation()
            if not install.installed:
                return AdapterStatus(self.id, AdapterState.NOT_INSTALLED, install.message or "Nicht gefunden.",
                                     requirement=self.install_hint())
            val = self.validate_configuration()
            if not val.ok:
                return AdapterStatus(self.id, AdapterState.NOT_CONFIGURED, "; ".join(val.errors),
                                     requirement="; ".join(val.errors), version=install.version)
            return AdapterStatus(self.id, AdapterState.AVAILABLE, install.message or "Bereit.",
                                 version=install.version)
        except Exception as exc:  # Status-Abfrage darf nie die Anwendung stoppen
            return AdapterStatus(self.id, AdapterState.ERROR, f"{type(exc).__name__}: {exc}")

    # ---- Hilfen -------------------------------------------------------------
    def install_hint(self) -> str:
        return ""

    def capability(self, kind: QueryKind) -> Optional[Capability]:
        return next((c for c in self.get_capabilities() if c.kind is kind), None)

    def supports(self, kind: QueryKind) -> bool:
        c = self.capability(kind)
        return bool(c and c.available)

    def _authorize(self, query: object, *, kind_expected: Optional[QueryKind] = None) -> AuthorizedQuery:
        aq = require_valid(query)
        if aq.adapter_id != self.id:
            from ..core.errors import UnauthorizedQueryError
            raise UnauthorizedQueryError("Autorisierung gilt fuer ein anderes Modul.")
        if kind_expected and aq.kind is not kind_expected:
            raise AdapterNotAvailable(f"{self.name}: Abfrageart {aq.kind.value} nicht unterstuetzt.")
        return aq

    def _raw(self, aq: AuthorizedQuery, started: str, payload: dict[str, Any], *, version: str = "",
             errors: Optional[list[str]] = None) -> RawResult:
        return RawResult(query_id=aq.query_id, case_id=aq.case_id, target_id=aq.target_id, adapter_id=self.id,
                         started_at=started, finished_at=now_iso(), payload=payload, tool_version=version,
                         errors=errors or [])
