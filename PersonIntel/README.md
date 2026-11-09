# PersonIntel

Eigenständiges, modulares OSINT-Modul für **journalistische Personenrecherche** auf dem
Linux-Desktop (Python + PySide6). PersonIntel bündelt zehn Recherchewerkzeuge unter einer
Oberfläche, hält jeden Befund an seine Quelle gebunden und erzwingt eine dokumentierte
Zweckbindung je Fall.

Es ist als **Teilmodul** gebaut: stabile Paket-Schnittstelle, versioniertes Austauschformat,
austauschbare Oberflächenteile und Plugin-Registrierung, damit es später mit einer bestehenden
System-OSINT-Anwendung verschmolzen werden kann (siehe [docs/FUSION.md](docs/FUSION.md)).

```
pip install -e '.[ui]'     # Oberfläche
personintel                # Start
personintel-cli status     # Betriebsstatus aller Module (headless)
```

Ausführliche Installation einschließlich der zehn Werkzeuge: [docs/INSTALL.md](docs/INSTALL.md).
Aufbau und Entwurfsentscheidungen: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Was PersonIntel ist – und was nicht

Es ist eine Rechercheplattform für legitime Personenrecherche: Verifikation von Quellen,
Überprüfung öffentlicher Angaben, Dokumentation für die Redaktion. Es ist **kein** Werkzeug für
heimliche Überwachung, Doxxing oder den Zugriff auf fremde Benutzerkonten. Das ist nicht nur eine
Absichtserklärung, sondern im Programm verankert:

| Grundsatz | Umsetzung |
|---|---|
| Zweckbindung | Ohne dokumentierten, befristeten Zweck (Kategorie, Beschreibung, Verantwortliche/r) ist **jede** Abfrage gesperrt. |
| Trennung passiv/aktiv | Abfragen, die fremde Dienste kontaktieren, sind als „aktiv“ gekennzeichnet, müssen im Zweck erlaubt und **pro Abfrage** gesondert bestätigt werden (Kennung erneut eingeben, zwei Hinweise bestätigen). |
| Kein Massenbetrieb | Genau eine Kennung pro Abfrage; Listen, Platzhalter und Mustersuchen werden abgewiesen. Pro Fall höchstens 10 Kennungen, 25 aktive Abfragen pro Tag, Mindestabstand zwischen Abfragen. |
| Belegpflicht | Jeder Befund trägt eine Belegstufe: **unmittelbar belegt**, **Indiz** oder **unbestätigt** – zusammen mit Quelle, Zeitstempel und Werkzeugversion. |
| Keine Leak-Zugangsdaten | Es werden keine privaten Leak-Datenbanken ausgewertet und keine Passwörter oder Hashes gespeichert oder angezeigt (Mosint-Ausgaben werden entsprechend gefiltert). |
| Keine Umgehung | Keine Konto-Übernahmen, kein Umgehen von CAPTCHAs, Zugangsbeschränkungen oder Rate-Limits. Rate-Limits beenden die Abfrage, statt sie zu unterlaufen. |
| Keine Identitätsgleichsetzung | Gleiche Benutzernamen gelten nie als Beweis für dieselbe Person. Verbindungen im Graphen entstehen ausschließlich manuell, mit Beleg und Begründung. |
| Datensparsamkeit | Rohantworten werden nicht gespeichert; Wohnadressen, Geburtsdaten und Verwandte werden aus Anbieterdatensätzen nicht übernommen. Daten bleiben lokal, sind verschlüsselbar und gezielt löschbar. |
| Nachvollziehbarkeit | Hash-verkettetes Protokoll jeder Freigabe, Ablehnung und Abfrage – ohne Kennungen im Klartext (HMAC-Pseudonyme). |

## Die zehn Module

| Modul | Eingabe | Art | Stand |
|---|---|---|---|
| **Holehe** | E-Mail | aktiv | Vollständig; nutzt die lokale `holehe`-Installation (CSV-Ausgabe). Module mit Rate-Limit werden als „möglicher Treffer“ gekennzeichnet, nicht als Treffer. |
| **Mosint** | E-Mail | aktiv | Vollständig; benötigt `mosint` samt eigener Konfigurationsdatei. Leak-Abschnitte werden auf Quellname und Datum reduziert, Passwörter und Hashes verworfen. |
| **Sherlock** | Benutzername | aktiv | Vollständig; `sherlock`-CSV. Treffer sind immer nur **Indiz** und werden nie automatisch einer Person zugeordnet. |
| **PhoneInfoga** | Telefonnummer | passiv | Vollständig; nutzt die lokale REST-Schnittstelle (nur an 127.0.0.1 gebunden), sonst die CLI-Ausgabe. Nummernmetadaten gelten nicht als Zuordnung zu einer Person. |
| **Ignorant** | Telefonnummer | aktiv | Vollständig; nutzt die Python-Umgebung von `ignorant`. Abfragen laufen seriell und brechen beim ersten Rate-Limit ab. |
| **Mr.Holmes** | Berichtsdatei | passiv | Erkennt die Installation und importiert vorhandene Mr.Holmes-Berichte (SHA-256 als Herkunftsnachweis). Mr.Holmes hat keine automatisierbare Schnittstelle; es wird daher nicht ferngesteuert. |
| **Pipl** | E-Mail, Telefon, Benutzername, Name | aktiv | Vollständig gegen die dokumentierte Search API; erfordert einen eigenen Pipl-Schlüssel. Verbindungstest nutzt den kostenlosen, vom Anbieter dokumentierten Testaufruf. |
| **Spokeo** | E-Mail, Telefon (nur US), Benutzername | aktiv | Vollständig gegen die dokumentierte API v5; erfordert einen Spokeo-API-Vertrag. |
| **ShadowDragon** | – | – | **Recherche nicht verfügbar.** Konfiguration und Status vorhanden; es gibt keine öffentliche API-Dokumentation. Voraussetzung: Vertrag, Anbieterdokumentation und Zugangsdaten. |
| **Babel Street** | – | – | **Recherche nicht verfügbar.** Die öffentlich dokumentierte API (Text Analytics) ist keine Personensuche. Voraussetzung: Zugang zur Identity-/Insight-API samt Dokumentation. |

Die beiden letzten Module erfinden bewusst keine Endpunkte und liefern keine erfundenen
Ergebnisse. Die Oberfläche zeigt „Nicht verfügbar (Anbieterzugang)“ und nennt die konkrete
Voraussetzung; eine Abfrage wird mit derselben Begründung abgelehnt.

Lokale Werkzeuge sind **nicht** mitgeliefert. Was nicht installiert ist, erscheint im Dashboard
als „Nicht installiert“ mit dem Installationsbefehl – die übrigen Module bleiben voll nutzbar.

## Oberfläche

* **Übersicht** – echter Betriebsstatus der zehn Module: installiert, konfiguriert, Version,
  Lizenz-/Verbindungsstand und die jeweils fehlende Voraussetzung.
* **Fälle** – Zweck dokumentieren und erneuern, Kennungen registrieren, Fall exportieren,
  importieren, gezielt löschen.
* **Recherche** – Formular je Eingabeart, deutliche Trennung passiv/aktiv, Bestätigungsdialog für
  aktive Prüfungen, laufende Abfragen mit Abbruch.
* **Ergebnisse** – Befunde mit Quelle, Zeitstempel und Belegstufe; Prüfvermerke des Bearbeiters
  (geprüft/verworfen, Belegstufe nur mit Begründung heraufsetzbar).
* **Verbindungen** – Graph der belegten Zusammenhänge; Kanten nur manuell, mit Basisbefunden.
* **Chronologie** – zeitlicher Ablauf der Recherche.
* **Bericht** – Dokumentation als Markdown, HTML, JSON oder PDF, mit Einschränkungshinweisen.
* **Einstellungen** – Konfiguration je Modul, verschlüsselter Zugangsdatenspeicher, Grenzen der
  Recherchekontrolle, nachträgliche Verschlüsselung der Datenbank.

## Tests

```
pip install -e '.[dev]'
python -m pytest -q
```

Die Tests prüfen die Zweck- und Berechtigungsprüfung (einschließlich gefälschter und
nachträglich veränderter Autorisierungen), die Manipulationserkennung des Protokolls,
Verschlüsselung und Löschen, die Datensparsamkeit der Adapter, Graph- und Berichtsregeln,
das Austauschformat sowie die Oberfläche (offscreen).

Die lokalen Werkzeuge werden dabei durch ausführbare Attrappen ersetzt, die deren **dokumentierte
Ausgabeformate** erzeugen, die Anbieter-APIs durch einen lokalen HTTP-Server. Damit werden die
echten Prozess-, Datei- und Parsing-Pfade getestet, ohne fremde Dienste zu kontaktieren.
Was damit *nicht* bewiesen ist, steht in [docs/INSTALL.md](docs/INSTALL.md) unter
„Was geprüft ist und was nicht“.

## Lizenz

MIT (siehe `pyproject.toml`). Die angebundenen Werkzeuge und Dienste haben eigene Lizenzen und
Nutzungsbedingungen; sie sind nicht Teil dieses Projekts.
