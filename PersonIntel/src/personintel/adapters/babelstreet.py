"""Babel Street - Konfiguration und Adaptervertrag.

Stand der Recherche (Nov. 2026): Oeffentlich dokumentiert ist die *Analytics-API* (Text Analytics,
developer.babelstreet.com, SDKs ``rosette_api``): Sprach-/Entitaetsanalyse von Texten, **keine**
Personensuche. Die "Insight APIs" (u. a. Identity API fuer personenbezogene Public-Records-Suche)
sind per Pressemitteilung angekuendigt, haben aber keine oeffentliche Endpunkt-Dokumentation.
Die Analytics-API waere fuer Personenrecherche der falsche Endpunkt und wird daher nicht verwendet.
Die Recherchefunktion ist deshalb nicht implementiert; Konfiguration und Status sind vollstaendig.
"""

from __future__ import annotations

from ._vendor_contract import VendorContractAdapter


class BabelStreetAdapter(VendorContractAdapter):
    id = "babelstreet"
    name = "Babel Street"
    vendor = "Babel Street"
    category = "Kommerzielle Rechercheplattformen"
    description = "Babel Street (Insight/Identity-APIs) – Konfiguration vorhanden, Recherche erfordert Anbieterfreigabe."
    homepage = "https://www.babelstreet.com"
    UNAVAILABLE_REASON = ("Die öffentlich dokumentierte Babel-Street-API (Analytics/Text Analytics) bietet keine "
                          "Personensuche; für die Identity-/Insight-API liegt keine öffentliche Dokumentation vor.")
    REQUIREMENT = ("Babel-Street-Vertrag mit Zugang zur Identity-/Insight-API, die zugehörige Anbieterdokumentation "
                   "(Basis-URL, Authentifizierung, Antwortschema) und Zugangsdaten.")
