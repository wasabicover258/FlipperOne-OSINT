"""Adaptervertrag fuer Anbieter ohne oeffentlich dokumentierte Personensuch-API.

Vollstaendige Konfigurationsoberflaeche (Schluessel, Basis-URL, Mandant) und transparenter Status;
die Recherchefunktion ist ausdruecklich *nicht verfuegbar*, bis Anbieterdokumentation und Freigabe
vorliegen. Es werden weder Endpunkte erfunden noch Ergebnisse simuliert.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional

from ..core.errors import AdapterNotAvailable
from ..core.models import NormalizedBatch, QueryKind, QueryMode
from ..security.authorization import AuthorizedQuery
from ._commercial import CommercialAdapter
from .base import (AdapterState, AdapterStatus, Capability, ConfigField, ConfigValidation, RawResult)


class VendorContractAdapter(CommercialAdapter):
    UNAVAILABLE_REASON: ClassVar[str] = ""
    REQUIREMENT: ClassVar[str] = ""
    SUPPORTED_KINDS: ClassVar[tuple[QueryKind, ...]] = (QueryKind.EMAIL, QueryKind.PHONE, QueryKind.USERNAME,
                                                       QueryKind.NAME)

    config_fields: ClassVar[tuple[ConfigField, ...]] = (
        ConfigField("api_key", "API-Schlüssel / Token", secret=True,
                    help="Vom Anbieter bereitgestellt. Wird verschlüsselt im Credential-Store abgelegt."),
        ConfigField("base_url", "API-Basis-URL (laut Anbieterdokumentation)",
                    help="Nur HTTPS. Wird vom Anbieter/Vertrag vorgegeben und hier nicht geraten."),
        ConfigField("tenant", "Mandant / Organisation (optional)"),
    )

    def missing_requirement(self) -> str:
        return self.REQUIREMENT

    def validate_configuration(self, config: Optional[dict[str, Any]] = None) -> ConfigValidation:
        cfg = config if config is not None else self.config
        errors: list[str] = []
        warnings: list[str] = []
        if not self.has_key():
            warnings.append("API-Schlüssel noch nicht hinterlegt.")
        base = str(cfg.get("base_url", "") or "")
        if base:
            from ..core.errors import AdapterError
            from ._http import safe_base_url
            try:
                safe_base_url(base, "")
            except AdapterError as exc:
                errors.append(str(exc))
        return ConfigValidation(not errors, errors, warnings)

    def get_capabilities(self) -> list[Capability]:
        return [Capability(k, QueryMode.ACTIVE, f"{self.name}: Suche nach {k.label_de}",
                           "Nicht verfügbar – siehe Voraussetzung.", available=False,
                           reason=self.UNAVAILABLE_REASON + " " + self.REQUIREMENT, cost_note=self.cost_note)
                for k in self.SUPPORTED_KINDS]

    def get_status(self) -> AdapterStatus:
        if not self.enabled:
            return AdapterStatus(self.id, AdapterState.DISABLED, "Modul ist deaktiviert.")
        val = self.validate_configuration()
        configured = self.has_key() and bool(self.config.get("base_url"))
        msg = ("Zugangsdaten hinterlegt, aber keine Recherchefunktion implementiert: " if configured
               else "Nicht verfügbar: ") + self.UNAVAILABLE_REASON
        if not val.ok:
            msg += " Konfigurationsfehler: " + "; ".join(val.errors)
        return AdapterStatus(self.id, AdapterState.UNAVAILABLE_VENDOR, msg, requirement=self.REQUIREMENT,
                             license_status="Zugangsdaten hinterlegt, Lizenz nicht prüfbar" if self.has_key()
                             else "keine Zugangsdaten", connection_status="nicht implementiert")

    def execute_authorized_query(self, query: AuthorizedQuery) -> RawResult:
        self._authorize(query)
        raise AdapterNotAvailable(f"{self.name}: {self.UNAVAILABLE_REASON}", self.REQUIREMENT)

    def normalize_results(self, raw: RawResult) -> NormalizedBatch:
        return NormalizedBatch(notes=[f"{self.name}: keine Daten – {self.UNAVAILABLE_REASON}"])
