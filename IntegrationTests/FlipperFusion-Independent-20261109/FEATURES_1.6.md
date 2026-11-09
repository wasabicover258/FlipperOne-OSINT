# ChatGPT Test 1.6 – unabhängige Quellen, nearest-first und Prüfnachweise

## Kernänderung
*Alle* eingelesenen OSM-POI-Objekte werden nach Entfernung zur eingegebenen Koordinate geordnet. Bei gleicher auf einen Meter gerundeter Entfernung entscheidet die stabile OSM-ID. Es gibt keine bevorzugte Kategorie und keine Quote für Kliniken, Gastronomie oder andere Branchen. Maximal **28** der von Overpass zurückgegebenen Objekte werden angezeigt. Die öffentlichen Overpass-Antworten sind wiederum begrenzt; die App ist kein vollständiger globaler POI-Index.

## Genau ein zusätzlicher Ansatz je Eingabetyp

| Eingabe | Bestehender Weg | Zusätzlicher Ansatz in 1.6 | Daten / praktische Einschränkung |
|---|---|---|---|
| Vollständiger Name | Wikidata, Wikipedia, GitHub-Kandidaten | **OpenAlex** Autorendatensätze | Eindeutige OpenAlex-IDs, ORCID und publizierte Zugehörigkeiten; nur *Kandidaten*, keine automatische Gleichsetzung und keine erfundenen E-Mails |
| Benutzername | 70+ Webseiten-Prüfungen | **GitHub-REST-Profil** (exakter Login) | Echte Benutzer-ID/URL, öffentliche Repositories, freiwillig veröffentlichter Profiltext/Website; keine Identitätsbehauptung |
| E-Mail-Adresse | MX, SPF, DKIM, DMARC, MTA-STS | **DANE-TLSA** des primären MX-Servers | Unabhängige DNS-Sicherheitsinformation; kein Postfach- oder Inhaberbeweis |
| Telefonnummer | E.164, Land, grober Leitungstyp | **Historische deutsche Ortsvorwahl** | Ortsnetzindikator bei Festnetz; keine aktuelle Position oder Halterdaten |
| IPv4 | RDAP, rDNS, ASN, Shodan InternetDB und eigene Checks | **IPWhois** zweiter Provider | Grober IP-Standort/Netzbetreiber zum Gegenprüfen, kein GPS des Endgeräts |
| IPv6 | RDAP, rDNS, ASN, Dienste | **IPWhois IPv6** | Gleicher unabhängiger Kontext und Abweichungen zu bestehenden Quellen |
| Domain / Website / URL | DNS, TLS, CT-Log, HTTP-Header | **Wayback Availability** | Vorhandene historische Webkopie mit Zeitstempel, kein unkontrollierter Crawl |
| GPS | OSM/Nominatim, Overpass POIs | **Wikipedia GeoSearch** | Koordinatengebundene Wikipedia-Artikel im Umkreis; Artikel sind keine automatische POI-Identifikation |
| Adresse / Ort | Nominatim → Koordinaten → Overpass | **Wikipedia GeoSearch** zum ersten Ortskandidaten | Zweite unabhängige Quelle für bekannte Orte |
| Firma | Wikidata/OSM → Website → DNS/ASN | **GLEIF LEI-Register** | Amtlich erfasste Rechtsträger, LEI, Rechtssitz, Status, nur wenn vorhanden |
| Organisation | Wikidata/OSM | **GLEIF LEI-Register** | Wie bei Firmen; Nichttreffer ist kein Beweis, dass eine Organisation nicht existiert |
| Handelsregisternummer | Register-Portal-Hinweise | **Exakter LEI-Registerlookup** bei 20-stelliger LEI | Direkte GLEIF-Abfrage; lokale HRB/HRA-Nummern brauchen weiterhin die zuständige Gerichtsbarkeit |
| Fahrzeugkennzeichen | Formatprüfung | **Begrenzte deutsche Zulassungsbezirksliste** | Offline Kontext von einigen bekannten Präfixen; kein Halterzugriff |
| Fahrzeugidentifikationsnummer | NHTSA vPIC DecodeVinValues | **NHTSA DecodeWMI** | Herstellerkennung der ersten 3 VIN-Zeichen aus eigener NHTSA-Schnittstelle |
| BTC-/EVM-Wallet | Format und Explorer-Link | **Blockstream Esplora BTC Address** | Öffentliche bestätigte BTC-Bilanz und Transaktionsanzahl; bei EVM bewusst kein falscher Cross-Chain-Lookup |
| ASN | RIPEstat AS-Overview, announced prefixes | **RIPE RIS Routing Status** | Beobachtete BGP-Prefixe/Nachbarn als unabhängige Messmethode |

## Getrennte Belege statt Personendossiers
Quellen werden benannt, Datensätze mit stabilen Kennungen gespeichert. Mehrdeutige Namens-Kandidaten werden nicht blind zusammengeführt. Verifikationsstufen sind Hinweise und keine Behauptung einer privaten Identität. Mehr aus einem Namen allein herauszuholen, insbesondere persönliche E-Mails, ist **ohne eine ausdrücklich veröffentlichte und einer Person belastbar zuzuordnende Quelle nicht zuverlässig möglich**. Es gibt keine geratenen Adressen, keine Leckdaten und keine Telefonnummern-Inhabersuche.

## Leistung
Optionaler Provider-Endpunkt: 4,5 Sekunden HTTP-Timeout und 384 KiB maximales JSON. Pro Eingabe höchstens wenige zusätzliche Endpunkte. Bisherige erfolgreiche Ergebnisse bleiben erhalten, wenn ein Zusatzprovider 404/429 oder einen Timeout liefert. Keine unbegrenzten Folgeabfragen. Gesamter CLI-Lauf ist weiterhin auf 150 Sekunden beschränkt.

## Teststand
- Neue Go-Tests: 40 synthetische POIs in steigender Entfernung; es müssen genau die **28 nächsten** erscheinen, unabhängig von Kategorien.
- Zusätzliche Tests: Provider-Timeout/-Größengrenzen und Fehlerstatus, GLEIF-Normalisierung, historische Ortsnetz-Vorwahl, Kennzeichenbezirke.
- Bestehende Tests: 294 UI-Prüfungen und bisherige Go-Tests.
- ARM64-Workflow erstellt neue `ChatGPT Test/ChatGPT-Test-1.6-aarch64.AppImage`; ältere Versionen bleiben unverändert.
- Der CI-Test verwendet kontrollierte Antworten. Er **beweist nicht**, dass jede externe Website aktuell erreichbar ist, und ersetzt keinen Emulator-Starttest.

## Prüfen im Emulator
1. `ChatGPT-Test-1.6-aarch64.AppImage` installieren.
2. GPS `48.086056, 11.556722` testen: Fundliste streng nach Entfernung; erster Treffer nicht nach Branche priorisiert.
3. Name eines öffentlich dokumentierten Wissenschaftlers testen: OpenAlex-Autorenkandidaten.
4. Firmenname mit LEI testen: Wikidata/OSM und separater GLEIF-Bereich.
5. `example.com` testen: archivierte Webseite nur wenn Internet Archive einen Snapshot liefert.
6. Eine öffentliche ASN `AS15169` testen: RIPEstat BGP-Daten.
7. Wenn ein Zusatzanbieter ausfällt, darf die bisherige Hauptsuche nicht abbrechen.

## Offizielle Quellen
- https://help.openalex.org/api/
- https://docs.github.com/en/rest/users/users
- https://www.gleif.org/en/lei-data/gleif-api/
- https://www.mediawiki.org/wiki/API:Geosearch
- https://guides.library.yale.edu/archivingwebresearchdata/waybackmachine
- https://www.ripe.net/analyse/internet-measurements/routing-information-service-ris/
- https://github.com/Blockstream/esplora/blob/master/API.md
- https://vpic.nhtsa.dot.gov/api/
- https://ipwhois.io/documentation
