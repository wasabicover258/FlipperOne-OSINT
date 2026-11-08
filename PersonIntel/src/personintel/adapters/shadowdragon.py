"""ShadowDragon (Horizon / SocialNet) - Konfiguration und Adaptervertrag.

Stand der Recherche (Nov. 2026): Fuer die ShadowDragon-API existiert nach oeffentlich auffindbaren
Quellen nur eine Kundendokumentation ("API documentation: yes", kein Sandbox - UK G-Cloud-Eintrag);
eine oeffentliche Endpunkt-/Schema-Beschreibung gibt es nicht. Deshalb ist die Recherchefunktion
nicht implementiert. Sobald Vertrag und Dokumentation vorliegen, genuegt eine Unterklasse mit
``execute_authorized_query``/``normalize_results`` - UI, Status, Zugangsdaten und Recherchekontrolle
sind bereits angebunden (siehe docs/ARCHITECTURE.md, "Neuen Anbieter anbinden").
"""

from __future__ import annotations

from ._vendor_contract import VendorContractAdapter


class ShadowDragonAdapter(VendorContractAdapter):
    id = "shadowdragon"
    name = "ShadowDragon"
    vendor = "ShadowDragon"
    category = "Kommerzielle Rechercheplattformen"
    description = "ShadowDragon Horizon/SocialNet – Konfiguration vorhanden, Recherche erfordert Anbieterfreigabe."
    homepage = "https://shadowdragon.io"
    UNAVAILABLE_REASON = ("Es ist keine öffentliche API-Dokumentation für die Personen-/Identitätssuche verfügbar; "
                          "Endpunkte werden nicht erraten und keine Ergebnisse simuliert.")
    REQUIREMENT = ("ShadowDragon-Vertrag mit API-Zugang, die kundenseitige API-Dokumentation (Basis-URL, "
                   "Authentifizierung, Antwortschema) und ein API-Schlüssel/Token.")
