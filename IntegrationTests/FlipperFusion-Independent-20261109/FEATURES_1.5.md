# ChatGPT Test 1.5 – Ortsrecherche und öffentliche Unternehmensdaten

## Ergebnis

Version 1.5 erweitert die bestehende OSINT-Anwendung um eine **echte Umkreissuche für öffentliche Einrichtungen und Unternehmen**. Sie ersetzt die reine Koordinatenanzeige nicht, sondern baut darauf auf. Bestehende technische Recherchen, die Namenssuche und die kategorisierte Ergebnisansicht aus 1.4 bleiben erhalten.

**Veröffentlichung:** `main/ChatGPT Test/ChatGPT-Test-1.5-aarch64.AppImage`.

## Neue Recherchekette

Bei einer GPS-Eingabe wie `48.086056, 11.556722`:

1. **Nominatim** versucht, den nächstliegenden kartierten Ort zu beschreiben (ein Haus-/Straßenname ist nicht immer die tatsächlich dort befindliche Einrichtung).
2. **Overpass API** sucht unabhängig davon einmalig im **500-m-Radius** nach öffentlichen Einrichtungen und Betrieben. Die Abfrage berücksichtigt `node`, `way`, `relation` mit einschlägigen Tags für Gesundheit, Restaurants, Geschäfte, Büros, Bildung, Hotels, Museen und öffentliche Dienstleistungen.
3. Die Antwort wird nach Entfernung geordnet und auf maximal **28 unterschiedliche Einrichtungen** begrenzt. Überlappende Kartenobjekte mit gleichem Namen und Typ werden zusammengeführt. In dicht bebauten Gegenden bleiben Plätze für Gesundheitseinrichtungen und Gastronomie reserviert.
4. Pro Einrichtung erscheinen, **nur wenn in OSM vorhanden**, Name, Typ (z. B. *Clinic*), Entfernung, offizielle Kartensource, öffentliche Geschäftsadresse, Telefonnummer, E-Mail und Website.
5. Gefundene Websites werden normalisiert, mit der zugehörigen Einrichtung als Graphkante gespeichert und für maximal **zwei unterschiedliche Websites** je Suchlauf per **DNS** zu öffentlichen IPs aufgelöst. Es werden **keine** privaten Netzwerkadressen gespeichert und **keine** automatischen Portscans auf abgeleitete Ziele ausgeführt.

Die Eingabe **Adresse / Ort** führt nach erfolgreichem Geocoding desselben ersten Ortskandidaten ebenfalls die Umkreissuche aus. **Firma / Organisation** ergänzt die bisherige Wikidata-/OSM-Recherche durch eine auf passende Namen eingeschränkte POI-Abfrage.

## Einheitlicher Ergebnisgraph

Stabile Ortsidentität = `place|<osm-type>/<osm-id>`. Dadurch verschmelzen zwei unterschiedliche Filialen nicht bloß wegen desselben Namens.

Aus einer öffentlichen Eintragung können folgende Kanten entstehen:

```text
Klinik (OSM-Way 101)
  |-- listed phone --> +49...
  |-- listed email --> info@...
  +-- listed website --> klinik.example
                              +-- resolves to --> oeffentliche IP
```

Jede Beziehung besitzt einen Quellenverweis und eine Belegstufe. OSM-Einträge sind **Hinweise aus einer öffentlichen Karte**, keine Garantie, dass Name oder Kontaktdaten noch aktuell sind.

In der Ergebnisoberfläche gibt es nun Untergruppen für **Kliniken/Gesundheit, Restaurants/Cafés und Geschäfte/Dienstleistungen**. Öffentliche geschäftliche Kontaktangaben erscheinen zusätzlich in **Telefonnummern/E-Mail-Adressen**, Webseiten unter **Organisationen → offizielle Websites**, DNS unter **Technik**.

## Funktionsüberblick nach Eingabe

| Ausgangspunkt | Status in 1.5 |
|---|---|
| GPS | Nominatim + neue Overpass-Radiusabfrage + OSM-Kontaktdaten + begrenztes Website/DNS-Pivot |
| Adresse / Ort | Nominatim-Geoauflösung → neue Overpass-POI-Abfrage |
| Firma / Organisation | Wikidata-Unternehmensdaten → Website/DNS/ASN; OSM-Geokandidat → gezielte POI-Abfrage |
| Domain / URL | Vorhandene technische DNS-, TLS-, Subdomain- und Infrastrukturmethoden |
| IPv4 / IPv6 | Vorhandene rDNS-, RDAP-, ASN-, Dienst- und Sicherheitslückenmethoden |
| Name | Vorhandene Wikidata-, Wikipedia- und GitHub-Kandidatenwege |
| Username | Vorhandene Prüfung öffentlich erreichbarer Plattformprofile |
| E-Mail / Telefon | Vorhandene technische Prüfungen; weiterführende Drittanbieterprüfungen nur mit den nötigen Zugängen und Freigaben |
| ASN | Vorhandene RIPEstat-Informationen und Routing-Präfixe |
| VIN / Wallet / Register / Kennzeichen | Vorhandene jeweils eingeschränkte öffentlichen Prüfwege |

Nicht alle Sucharten besitzen dieselben öffentlich zugänglichen Datenquellen. **Die Erweiterung von 1.5 verbessert die Orts-, Adress- und Organisationssuche; sie erzeugt keine automatisch vollständigen Personenprofile.**

## Nachweise

Der native ARM64-GitHub-Actions-Workflow prüft:

- `go test ./...` einschließlich Offline-HTTP-Fixtures für Klinik/Restaurant, Overpass-Anfrage, Quellenfelder, Duplikaterkennung, Graphbeziehungen und Fehlermeldung bei API-Rate-Limits.
- `osint-ui --selftest` einschließlich Gruppierung der neuen Klinik-, Restaurant-, Telefon-, E-Mail- und Website-Ergebnisse.
- AppImage-AArch64-Architektur und Veröffentlichung mit SHA-256-Prüfsumme.

**Wichtig:** Offline-Fixtures prüfen den Verarbeitungspfad, nicht die Existenz oder Vollständigkeit realer Klinikdaten in OpenStreetMap. Ein echter Test der GPS-Abfrage am physischen/emulierten Flipper-One-Linux-System und ein erfolgreicher Abruf auf dem externen Overpass-Server stehen weiterhin aus.

## Betriebsgrenzen

- **OpenStreetMap-Abdeckung:** Fehlt ein Eintrag, kann die App ihn dort nicht finden; Kontaktdaten können unvollständig oder veraltet sein.
- **Overpass:** Freier geteilter Dienst, mögliche HTTP 429 / 502 / 504. Kein garantiertes Antwortzeitfenster; Anfragen und Ausgabe sind begrenzt. Ein eigener Overpass-Server wäre bei regelmäßiger intensiver Nutzung vorzuziehen.
- **Nominatim:** Maximal eine Anfrage pro Sekunde an die öffentliche OSMF-Instanz, erkennbare User-Agent-Kennung und Quellenangabe erforderlich.
- **Google Maps Places:** Nicht eingebaut. Die offizielle Nearby-Search-API benötigt einen Google-API-Schlüssel mit aktivierter Abrechnung und kostenabhängige FieldMasks für Website/Telefon; kein unzulässiges Maps-Scraping.
- **Python/PersonIntel:** Externe Python-Programme und proprietäre APIs sind nicht durch die neue Kartenlogik automatisch mitinstalliert.
- **Privatsphäre:** Keine Hausbewohner-/Eigentümerrecherche und keine unbegrenzte automatische Identitätsverkettung.

## Testen im Emulator

1. Die neue AppImage 1.5 in den File Manager ziehen und installieren.
2. Falls neue App-Einträge erst nach einem Gast-Neustart sichtbar sind, **nur das emulierte Flipper OS normal neu starten** (kein Factory Reset).
3. GPS auswählen und `48.086056, 11.556722` eingeben.
4. Den Abschnitt **Nearby facilities and businesses (500m)** sowie **Places & maps → Clinics & healthcare** öffnen.
5. Bei einem gefundenen Betrieb die öffentlichen Kontaktdaten und den OSM-Quellenlink prüfen.
6. Vergleich: Einen bekannten Restaurantpunkt und eine öffentliche Firmenadresse testen.
7. Bei 429/504 oder leeren Ergebnissen die Originalmeldung aus dem UI weitergeben; kein Erfolg darf lediglich aus einem grünen Build abgeleitet werden.

Technische Quellen: [Overpass-Ql-Dokumentation](https://dev.overpass-api.de/overpass-doc/en/full_data/polygon.html), [Nominatim-Nutzungsbedingungen](https://operations.osmfoundation.org/policies/nominatim/), [Google Places Nearby Search](https://developers.google.com/maps/documentation/places/web-service/nearby-search).
