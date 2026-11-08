"""Gemeinsame Basis kommerzieller Connectoren (Cloud-APIs mit vom Nutzer bereitgestellten Zugangsdaten)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, ClassVar, Optional

from ..core.errors import AdapterError, AdapterNotAvailable, QueryCancelled
from ..core.ids import now_iso
from ..core.models import NormalizedBatch
from .base import (Adapter, AdapterState, AdapterStatus, ConfigField, ConfigValidation, InstallInfo)


@dataclass
class ConnectionState:
    state: str = "unknown"   # unknown | ok | invalid_credentials | error
    message: str = ""
    checked_at: str = ""


class CommercialAdapter(Adapter):
    """Anbieter-Connector. Geheimnisse kommen ausschliesslich aus dem Credential-Store."""

    config_fields: ClassVar[tuple[ConfigField, ...]] = (
        ConfigField("api_key", "API-Schlüssel", secret=True, required=True,
                    help="Wird verschlüsselt im Credential-Store abgelegt, nie im Klartext gespeichert."),
        ConfigField("include_contact_details", "Kontaktdaten (Telefon/E-Mail) übernehmen",
                    help="'true' übernimmt Telefonnummern/E-Mail-Adressen aus Anbieterdatensätzen. "
                         "Wohnadressen, Verwandte und Geburtsdaten werden nie übernommen.", default="false"),
        ConfigField("base_url", "Basis-URL (nur für Tests/Gateways)",
                    help="Standard ist die offizielle Anbieter-URL. Nur HTTPS (oder http://localhost)."),
    )

    vendor: ClassVar[str] = ""
    cost_note: ClassVar[str] = "Kostenpflichtige Abfrage (Vertrag/Kontingent des Anbieters)."

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._conn = ConnectionState()
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    # ---- gemeinsame Pflichtmethoden ---------------------------------------
    def detect_installation(self) -> InstallInfo:
        return InstallInfo(True, message="Cloud-API – keine lokale Installation erforderlich.")

    def has_key(self) -> bool:
        return self.secrets.has("api_key")

    def api_key(self) -> str:
        key = self.secrets.get("api_key")
        if not key:
            raise AdapterNotAvailable(f"{self.name}: API-Schlüssel fehlt.", self.missing_requirement())
        return key

    def missing_requirement(self) -> str:
        return f"{self.vendor}-API-Schlüssel (Vertrag/Account beim Anbieter) im Credential-Store hinterlegen."

    def validate_configuration(self, config: Optional[dict[str, Any]] = None) -> ConfigValidation:
        errors: list[str] = []
        if not self.has_key():
            errors.append("API-Schlüssel fehlt.")
        cfg = config if config is not None else self.config
        base = str(cfg.get("base_url", "") or "")
        if base:
            from ._http import safe_base_url
            try:
                safe_base_url(base, "")
            except AdapterError as exc:
                errors.append(str(exc))
        return ConfigValidation(not errors, errors)

    def include_contacts(self) -> bool:
        return str(self.config.get("include_contact_details", "false")).strip().lower() in ("1", "true", "yes", "ja")

    # ---- Abbruch ------------------------------------------------------------
    def cancel_query(self, query_id: str) -> bool:
        with self._lock:
            self._cancelled.add(query_id)
        return True

    def _check_cancel(self, query_id: str) -> None:
        with self._lock:
            if query_id in self._cancelled:
                self._cancelled.discard(query_id)
                raise QueryCancelled("Abfrage abgebrochen.")

    # ---- Status ---------------------------------------------------------------
    def license_text(self) -> str:
        return "nicht prüfbar"

    def get_status(self) -> AdapterStatus:
        if not self.enabled:
            return AdapterStatus(self.id, AdapterState.DISABLED, "Modul ist deaktiviert.")
        val = self.validate_configuration()
        if not val.ok:
            return AdapterStatus(self.id, AdapterState.NOT_CONFIGURED, "; ".join(val.errors),
                                 requirement=self.missing_requirement(), license_status="keine Zugangsdaten",
                                 connection_status="keine Verbindung")
        c = self._conn
        if c.state == "ok":
            return AdapterStatus(self.id, AdapterState.AVAILABLE, c.message or "Zugang funktioniert.",
                                 license_status=self.license_text(), connection_status=f"verbunden ({c.checked_at})")
        if c.state == "invalid_credentials":
            return AdapterStatus(self.id, AdapterState.ERROR, c.message or "Zugangsdaten abgelehnt.",
                                 requirement="Gültigen API-Schlüssel mit freigeschalteter Lizenz hinterlegen.",
                                 license_status="abgelehnt", connection_status=f"abgelehnt ({c.checked_at})")
        if c.state == "error":
            return AdapterStatus(self.id, AdapterState.UNVERIFIED, c.message,
                                 license_status="unbekannt", connection_status=f"Fehler ({c.checked_at})")
        return AdapterStatus(self.id, AdapterState.UNVERIFIED,
                             "Zugangsdaten hinterlegt; Zugang wurde noch nicht verifiziert.",
                             license_status=self.license_text(), connection_status="nicht geprüft")

    def _set_conn(self, state: str, message: str = "") -> None:
        self._conn = ConnectionState(state, message, now_iso())

    def _http_error(self, status: int, body_hint: str = "") -> AdapterError:
        """Uebersetzt HTTP-Status in verstaendliche Fehler und merkt den Verbindungsstatus."""
        hint = f" ({body_hint[:160]})" if body_hint else ""
        if status in (401, 403):
            msg = f"{self.name}: Zugang abgelehnt (HTTP {status}) – Schlüssel ungültig oder Lizenz fehlt{hint}."
            self._set_conn("invalid_credentials", msg)
        elif status == 429:
            msg = f"{self.name}: Kontingent/Rate-Limit erreicht (HTTP 429){hint}. Es wird nicht automatisch wiederholt."
            self._set_conn("error", msg)
        else:
            msg = f"{self.name}: Anfrage fehlgeschlagen (HTTP {status}){hint}."
            self._set_conn("error", msg)
        return AdapterError(msg)

    # Standard-Normalisierung leer, falls Unterklasse nichts liefert
    def normalize_results(self, raw) -> NormalizedBatch:  # pragma: no cover - ueberschrieben
        return NormalizedBatch()
