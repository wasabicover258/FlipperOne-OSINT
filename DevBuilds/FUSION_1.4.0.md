# Fusion FlipperOne-OSINT × PersonIntel – Version 1.4.1

Zusammenführung der bestehenden Flipper-One-App (C/SDL2 + Go) mit dem PersonIntel-Modul
(Python) zu **einer** App. Dieses Dokument ist der Abschlussbericht zur Fusion.

| | |
|---|---|
| Branch | `fusion/flipper-personintel` |
| Ausgangspunkt | `742f346` (PersonIntel fertiggestellt, `main` unberührt) |
| AppImage | `DevBuilds/FlipperOne-OSINT-1.4.1-aarch64.AppImage` (1.4.0 bleibt daneben bestehen) |
| Prüfsumme | `DevBuilds/FlipperOne-OSINT-1.4.1-aarch64.AppImage.sha256` |
| Gebaut von | `.github/workflows/build-appimage-fusion.yml` auf einem ARM64-Runner |

`main`, `Public Releases/` und alle vorhandenen AppImages sind unverändert.

---

## 1. Architektur und warum sie so gewählt ist

Die beiden Hälften sind technisch sehr verschieden: die Flipper-App ist ein 80-KB-C-Binary mit
SDL2 plus ein statisches Go-Backend, PersonIntel ist Python mit PySide6-Oberfläche.

Entscheidend für die Wahl war die Zielumgebung. Der Emulator gibt dem Gast 2–4 GB RAM mit
reiner Software-Emulation (QEMU TCG) und ohne GPU; hosted apps rendern über einen
Software-Compositor. Ein PySide6-Bündel wäre rund 250 MB und müsste Qt darüber zeichnen.

Gewählt wurde daher:

- **Die SDL2-Oberfläche bleibt die einzige Oberfläche** und wurde um die Personenmodule
  erweitert. Die Flipper-Tastenbedienung (`Z X C V B`, D-Pad, Touch) gilt unverändert auch für
  die neuen Schirme.
- **Die geprüften Regeln bleiben, wo sie getestet sind.** Zweckbindung, Belegstufen,
  Bestätigung aktiver Prüfungen und das Protokoll liegen weiterhin in PersonIntel; sie wurden
  *nicht* in Go nachgebaut.
- **Die Verbindung ist ein kurzlebiger Prozess.** Das Go-Backend startet
  `personintel-cli bridge` und spricht zeilenweises JSON über stdin/stdout. Der Prozess läuft
  nur während einer Aufgabe und endet mit ihr — es bleibt kein Dienst zurück.
- **PersonIntel reist im Bündel mit**, als 540 KB reines Python unter
  `usr/lib/personintel`, ausgeführt mit dem Python des Geräts.

Fehlt auf dem Gerät ein Python ≥ 3.10, melden die Personenmodule genau das und die
Infrastrukturmodule arbeiten unverändert weiter.

## 2. Integrierte Module

**Unverändert übernommen** (fünf Module, identische Ausgabe):

| Modul | Eingabe | Prüfung |
|---|---|---|
| Username | Benutzername | 70+ Plattformen, nach Kategorie gruppiert |
| Email address | E-Mail | Provider, MX, SPF/DMARC/DKIM/MTA-STS |
| Phone number | Telefonnummer | Land, Format, Leitungsart (offline) |
| Domain / recon | Domain | DNS, DNSSEC, AXFR, Subdomains, Portscan, CVEs, Korrelation, Entitätsgraph |
| IP address | IP | rDNS, ASN, RDAP, Portscan, Banner, CVEs |

**Neu über PersonIntel** (zehn Module):

| Modul | Eingabe | Prüfung | Stand im Bündel |
|---|---|---|---|
| Holehe | E-Mail | aktiv | braucht `holehe` auf dem Gerät |
| Mosint | E-Mail | aktiv | braucht `mosint` + eigene Konfigurationsdatei |
| Sherlock | Benutzername | aktiv | braucht `sherlock` |
| PhoneInfoga | Telefon | passiv | braucht `phoneinfoga` |
| Ignorant | Telefon | aktiv | braucht `ignorant` |
| Mr.Holmes | Berichtsdatei | passiv | Import vorhandener Berichte, ohne Installation nutzbar |
| Pipl | E-Mail, Telefon, Benutzername, Name | aktiv | braucht Vertrag + Schlüssel |
| Spokeo | E-Mail, Telefon (US), Benutzername | aktiv | braucht Vertrag + Schlüssel |
| ShadowDragon | — | — | **nicht verfügbar**: keine öffentliche API-Dokumentation |
| Babel Street | — | — | **nicht verfügbar**: die dokumentierte API ist Textanalyse, keine Personensuche |

**Neu an Bedienelementen:** Modulstatus, Fall & Zweck, vier Personenabfragen, Berichtsimport,
Verbindungen, Bericht. Das Menü hat damit 14 Einträge und scrollt.

## 3. Was die App verweigert

Diese Punkte sind durch Tests abgedeckt, nicht nur dokumentiert:

- Ohne dokumentierten, unverfallenen Zweck wird **jede** Personenabfrage abgelehnt.
- Aktive Prüfungen starten nie direkt: der Bestätigungsschirm zeigt die Kennung erneut und
  verlangt zwei Haken. Erst dann erhält das Backend das Wort `confirm`; ohne dieses Wort lehnt
  PersonIntel ab. Abbrechen sendet nichts.
- Eine Kennung pro Abfrage, höchstens zehn pro Fall, Tagesbudget und Mindestabstand für aktive
  Prüfungen.
- Ein Treffer ist ein Hinweis. `=` belegt, `~` Indiz, `?` unbestätigt — und `=` setzt
  ausschließlich ein Mensch beim Prüfen, nie ein Modul. Gleicher Benutzername auf zwei
  Plattformen ist ein Hinweis, keine Verbindung.
- Leak-Abschnitte werden auf Quellname und Datum reduziert; Passwörter und Hashes werden
  verworfen. Adressen, Geburtsdaten und Verwandte werden aus Anbieterdatensätzen nicht übernommen.
- Rate-Limits beenden eine Abfrage, statt umgangen zu werden.

## 4. Gemeinsames Ergebnis- und Graphmodell

`app-ordner/src/cli/findings.go`. Beide Hälften schreiben in denselben Speicher:

- Jeder Eintrag nennt **Quelle, Zeitstempel, Werkzeugversion und Belegstufe**.
- **Duplikaterkennung** über normalisierte Schlüssel: Telefonformate und Hostschreibweisen
  verschmelzen, ein Konto wird über seine Profil-URL identifiziert — gleicher Handle auf zwei
  Plattformen bleibt deshalb zwei Konten.
- Melden zwei Quellen denselben Treffer, entsteht **ein** Eintrag mit zwei Quellen; die höhere
  Belegstufe gewinnt, eine schwächere Quelle senkt sie nie.
- **Kanten** tragen höchstens die Belegstufe ihres schwächeren Endes.
- **Folgeabfragen** werden nur als Kandidaten gelistet. Nichts wird automatisch abgefragt; der
  Fallumfang begrenzt, wie viele Kennungen ein Fall überhaupt aufnehmen kann.

Damit die Zusammenführung greifen kann, laufen in den Modi `Person: username`, `Person: email`
und `Person: phone` das Infrastrukturmodul und die Personenmodule in **einem** Prozess.

## 5. Vergleich mit 1.3.0

Gemessen auf einem x86_64-Host, nicht auf dem Gerät (Methode:
`osint-ui` mit dem SDL-Dummy-Treiber, Median aus fünf Läufen; Startzeit bis zur ersten
Ausgabe nach der SDL-Initialisierung, Speicher als `VmHWM`, CPU über `/proc/<pid>/stat`):

| | 1.3.0 | 1.4.0 | Differenz |
|---|---|---|---|
| Start der Oberfläche | 4,5 ms | 4,4 ms | −0,1 ms |
| RAM im Leerlauf | 7,7 MiB | 7,8 MiB | +0,1 MiB |
| CPU im Leerlauf | 0,8 % | 0,8 % | ±0 |
| Oberfläche (Binary) | 55,5 KB | 80,1 KB | +24,6 KB |
| Backend (Binary) | 6,36 MB | 6,53 MB | +0,17 MB |
| PersonIntel im Bündel | — | 540 KB | +540 KB |
| `phone`-Lauf | 3 ms | 2 ms | zeichengleiche Ausgabe |

Kosten der Personenmodule, die nur bei ihrer Benutzung anfallen:

| Aufruf | Zeit | Speicher |
|---|---|---|
| Personenmodul, Brücke vorhanden | 146 ms | 34 MiB, danach beendet |
| Personenmodul, kein Python auf dem Gerät | 51 ms | 13 MiB, meldet die Voraussetzung |

Die Oberfläche startet also unverändert schnell, und im Leerlauf läuft kein zusätzlicher
Prozess.

## 6. Testergebnisse

Ausgezählt, nicht geschätzt:

| Suite | Umfang | Was sie prüft |
|---|---|---|
| PersonIntel (Python) | **195 Tests** | Zweckprüfung, gefälschte Autorisierungen, Protokollmanipulation, Verschlüsselung, Adapter gegen Attrappen und lokalen HTTP-Server, Graph, Bericht, Austauschformat, Oberfläche, Brückenprotokoll, Betrieb ohne `cryptography`/`phonenumbers` |
| Backend (Go) | **15 Tests** | Duplikaterkennung, Belegstufen-Obergrenzen, Kanten, Folgekandidaten, Anbieterdatensatz bleibt Indiz, ASCII-Abbildung, Brückensuche |
| Oberfläche (C) | **168 Prüfungen** | Menü-Erreichbarkeit und Scrollen, Bestätigungspflicht aktiver Prüfungen, Modi ohne Eingabe, Marker-Zuordnung, Texteingabe, 4500 Ergebniszeilen |

Alle drei laufen im Workflow vor dem Bau. Zusätzlich prüft der Workflow am **fertigen
AppImage**, dass das mitgelieferte PersonIntel startet, alle zehn Module meldet und eine
Abfrage ohne dokumentierten Zweck blockiert bleibt.

Während der Fusion gefundene und behobene Fehler:

1. Die Duplikaterkennung verschmolz zwei verschiedene Konten mit gleichem Benutzernamen zu
   einem Eintrag.
2. Deutsche Anführungszeichen und weitere Satzzeichen wurden auf dem Display zu Fragezeichen.
3. Ein Oberflächentest flackerte, weil Warteschleifen Qt-Ereignisse ohne Pause verarbeiteten.
4. Der erste Workflow-Lauf scheiterte an fehlenden Qt-Systembibliotheken des Runners.

## 7. Emulator

**Nicht getestet.** Der Rechner ist zwar mit der Sitzung verbunden, der Zugriff auf einen
Ordner wurde jedoch vom Sicherheitsfilter dieser Sitzung blockiert, bevor eine Anfrage beim
Nutzer ankam. Damit konnte weder das AppImage abgelegt noch der File Manager oder die
Emulatoroberfläche bedient werden.

Das Testverfahren liegt in [EMULATOR_TEST_1.4.0.md](EMULATOR_TEST_1.4.0.md): 30 Schritte mit
jeweils erwartetem Ergebnis, dazu die Liste der Ausgaben, die für eine Auswertung nötig sind.
Bis diese vorliegen, gilt der Emulatorteil als ungetestet.

## 8. Ehrliche Lückenliste

**Nicht getestet, weil die Voraussetzungen fehlen:**

- Lauf im Emulator oder auf echter Flipper-One-Hardware (siehe oben).
- Ob Flipper OS überhaupt ein `python3` ≥ 3.10 mitbringt. Beide Fälle sind im Code behandelt
  und im Testverfahren beschrieben, aber welcher eintritt, ist offen.
- Die echten Recherchewerkzeuge: holehe, mosint, sherlock, phoneinfoga, ignorant waren in der
  Entwicklungsumgebung nicht installiert. Getestet wurde gegen ausführbare Attrappen mit den
  dokumentierten Ausgabeformaten. Besonders zu prüfen sind das JSON-Schema von Mosint und die
  Textausgabe der PhoneInfoga-CLI; beide sind nicht formal spezifiziert.
- Echte Abfragen bei Pipl und Spokeo (kostenpflichtig, Vertrag nötig). Getestet gegen einen
  lokalen HTTP-Server mit dem dokumentierten Antwortformat.
- Mr.Holmes-Berichte echter Installationen: der Import ist gegen die Textstruktur geprüft,
  nicht gegen alle Berichtsvarianten.

**Fehlende Abhängigkeiten und ihre Folgen:**

| Fehlt | Folge | Umgehung |
|---|---|---|
| `python3` ≥ 3.10 auf dem Gerät | keine Personenmodule | Infrastrukturmodule laufen weiter |
| `cryptography` (nicht im Bündel: `cffi` hat kein interpreterunabhängiges Wheel) | keine Verschlüsselung ruhender Daten, kein verschlüsselter Zugangsdatenspeicher auf dem Gerät | Anbieterschlüssel über `PERSONINTEL_<MODUL>_<FELD>`; auf dem Desktop ist beides verfügbar |
| `phonenumbers` (24 MB Metadaten) | strengere Nummernprüfung entfällt | E.164-Grundprüfung bleibt; durch Test abgedeckt |
| Werkzeuge der Personenmodule | das jeweilige Modul meldet seine Voraussetzung | die übrigen Module laufen |

**Lizenzen:** Dieses Projekt steht unter MIT. Die angebundenen Werkzeuge und Dienste haben
eigene Lizenzen und Nutzungsbedingungen und sind **nicht** Teil des Bündels — sie werden auf
dem Gerät gesucht, nicht mitgeliefert. Für Pipl und Spokeo gelten die Verträge des Nutzers;
für ShadowDragon und Babel Street fehlt die Freigabe, weshalb dort keine Recherchefunktion
existiert. Welche Lizenz die einzelnen Werkzeuge haben, wurde für diese Arbeit **nicht**
geprüft.

**Bewusst nicht umgesetzt:** eine Qt-Oberfläche auf dem Gerät (Größe und Rendering, siehe
Abschnitt 1); das Nachbauen der PersonIntel-Regeln in Go (Doppelpflege und Risiko, die geprüfte
Fassung zu verlieren); automatische Folgeabfragen (sie würden den dokumentierten
Untersuchungsumfang aushöhlen).
