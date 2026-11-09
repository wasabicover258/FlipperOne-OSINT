# Funktionsnachweis – ChatGPT Test 1.3 / 1.3.1

Diese Matrix beschreibt **ausgeführten Quellcode**, nicht bloße Feature-Wünsche. Sie garantiert keine live erreichbaren Provider und keinen erfolgreichen Emulatorstart.

## Eingabetypen und konkrete Bearbeitung

| Eingabe im Menü | CLI | Tatsächliche Quellen/Logik | Automatischer Schritt |
|---|---|---|---|
| Telefonnummer | `combo-phone` | E.164-Lokalprüfung; PersonIntel-Connectoren nur mit Python, Konfiguration und erlaubter aktiver Prüfung | Lokale Prüfung + bei Voraussetzungen ein kombinierter Durchlauf |
| E-Mail | `combo-email` | E-Mail-, Provider- und DNS/Mail-Sicherheitsprüfung; optional PersonIntel | Gemeinsame Ergebnisanzeige; Provider-Abfragen bleiben autorisierungspflichtig |
| Username | `combo-username` | Bestehende Prüfung von 70+ öffentlichen Plattformen; optional PersonIntel | Ein gemeinsamer Durchlauf bei verfügbaren Modulen |
| Vollständiger Name | `person-name` | Wikidata (inkl. dort verlinkten öffentlichen Social-Profilen), Wikipedia-Suche, öffentliche GitHub-Benutzer-Kandidaten | Drei öffentliche Suchwege; keine Gleichsetzung bloß ähnlicher Namen |
| IPv4 | `ipv4` | Bestehende IP-Auswertung inkl. rDNS, RDAP, ASN, CPE, CVE, Port-Checks | IP validieren und bestehende Infrastruktur-Engine starten |
| IPv6 | `ipv6` | Wie IPv4 mit IPv6-Validierung | IP validieren, gleiche Infrastruktur-Engine |
| Domain, Subdomain, URL | `website` | URL-Host normalisieren; bestehende Domain-Engine DNS, Mail-Security, TLS, HTTP-Fingerprinting, Subdomains, Infrastrukturgraph | URL → Hostname → bestehende Domain-Untersuchung |
| GPS-Koordinaten | `gps` | Bereichsvalidierung, OpenStreetMap-Kartenlink und Nominatim-Reverse-Geocoding | Koordinate → öffentliches Kartenobjekt |
| Adresse | `address` | OSM/Nominatim-Suche, bis zu 3 Kartenobjekte und Koordinaten | Adresse → Koordinaten |
| Firmenname | `company` | Wikidata-Unternehmens-/Organisationskandidaten mit offiziellen Websites und Organisationsbezügen; OSM-Ortskandidaten | Offizielle Website → DNS, max. 3 öffentliche IPs |
| Organisation | `organization` | Wie Firmenname | Belegter Webauftritt → DNS |
| Handelsregisternummer | `registry` | Format-/Eingabeprüfung, offizielle deutsche und britische Registerportale | **Kein** automatisches Register-Matching |
| Kennzeichen | `plate` | Lokale Eingabeprüfung, keine Halter- oder Tracking-Suche | **Kein** personenbezogener Lookup |
| Fahrzeugidentifikationsnummer | `vin` | 17-stellige VIN-Prüfung, Prüfziffer (NA-Regel), NHTSA-vPIC-Fahrzeugdaten | VIN → Hersteller/Modell/Fahrzeugtyp/Baujahr soweit verfügbar |
| Wallet-Adresse | `wallet` | EVM-/Bitcoin-Formatindikatoren, öffentliche Explorer-Links | **Keine** automatischen Transaktions- oder Inhaber-Abfragen |
| ASN | `asn` | RIPEstat AS-Overview und Announced-Prefixes | ASN → Holder und bis zu 12 öffentlich angekündigte Präfixe |

## Duplikate und quellenbasierter Graph

Die gemeinsame `Store`-Implementierung unter `app-ordner/src/cli/findings.go` führt Einträge anhand normalisierter Schlüssel zusammen und erhält mehrere unabhängige Quellen. Namen allein dienen **nicht** als sichere Personenschlüssel: Personen aus Wikidata werden mit ihrer Q-ID, Accounts über ihre Profil-URL identifiziert. Der Organisation-zu-Webseite-zu-IP-Pfad benutzt `Store.Link` mit Herkunftshinweisen.

Keine unbegrenzte Rekursion und keine selbsttätigen Identitätsprofile aus Telefonnummern, Adressen oder anderen persönlichen Kennungen. Technische Folgeabfragen sind bewusst begrenzt.

## Eingebaute Prüfbarkeit

- `go test ./...` auf ARM64 testet unter anderem URL-/GPS-Validierung, lokale IP-Sperre bei Organisationspivots, VIN-Prüfziffer, zwei Quellen für denselben Eintrag und kantenseitige Duplikaterkennung.
- `osint-ui --selftest` prüft Menü-Navigation, UI-State, Eingabe, Bestätigungszustände und große Ergebnislisten.
- Das GitHub-Actions-Skript prüft Architektur und erzeugt SHA-256. Es beweist nicht, dass alle Internetdienste verfügbar sind.
- Externe API-Dienste, Geocoding-Limits und die Python-Brücke sind auf dem **echten** Flipper-OS-Emulator noch nicht live geprüft.

## Was fehlt

Keine allgemeine Websuchmaschine, keine automatisch behaupteten Privatpersonen-Identitäten, keine vollständige Auswertung von Bildmetadaten, Einkommens-/Handelsregisterdaten, Social-Feeds, früheren Handles, Konto-Historien oder historischen Satellitenbildern. Pipl, Spokeo, ShadowDragon und Babel Street sind weiterhin abhängig von autorisierten, offiziell unterstützten API-Zugängen; einige haben für die gewünschten Abfragen keine allgemein dokumentierte API. `PersonIntel` benötigt eine kompatible Python-Laufzeit auf dem Zielgerät; die vorhandenen externen Rechercheprogramme sind nicht automatisch alle im ARM64-AppImage enthalten.

**Status:** Version 1.3 wurde gebaut. Version 1.3.1 ergänzt eine identifizierbare Nominatim-Anwendungskennung und einen gesonderten Test für Geocoding-HTTP-Antworten. Für beide gilt: AppImage-Build erfolgreich ≠ Emulatorstart oder reale Anbieterrecherche bestätigt.
