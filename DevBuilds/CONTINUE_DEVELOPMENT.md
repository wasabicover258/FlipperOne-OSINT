# PersonIntel – Stand der Entwicklung

Letzte Aktualisierung: 2026-11-09. Der am 08.11. gesicherte Zwischenstand ist inzwischen
**fertiggestellt**. Diese Datei beschreibt den aktuellen Stand, was belegt ist, was nicht, und
woran weitergearbeitet werden kann.

| | |
|---|---|
| Repo | `wasabicover258/FlipperOne-OSINT` |
| Branch | `dev/personintel-wip` (`main` und alle vorhandenen AppImages unverändert) |
| Projektordner | `PersonIntel/` |
| Umfang | ~7.800 Zeilen Code, 170 Tests, alle grün |
| Einstieg | `cd PersonIntel && pip install -e '.[dev,ui]' && python -m pytest -q` |

Hinweis zum Ablageort: PersonIntel ist ein **eigenes Projekt** (Linux-Desktop, Python/PySide6) und
liegt nur deshalb hier, weil dies das einzige angebundene Repository mit `DevBuilds/` war. Die
README von FlipperOne-OSINT schließt personenbezogene Dienste für die Flipper-App ausdrücklich
aus. Für ein eigenes Repository genügt es, den Ordner `PersonIntel/` zu verschieben.

## Fertig und geprüft

* **Kern:** Modelle mit versioniertem Ergebnisformat, strikte Eingabevalidierung (genau eine
  Kennung, E.164), Einstellungen, Engine-Fassade, Jobverwaltung, Plugin-Registry.
* **Recherchekontrolle:** dokumentierter, befristeter Zweck pro Fall; HMAC-signierte
  Autorisierungen; Trennung passiv/aktiv mit Pflichtbestätigung je aktiver Abfrage; Fallumfang,
  Tagesbudget, Mindestabstand; hash-verkettetes Protokoll ohne Kennungen im Klartext.
* **Speicher:** SQLite mit Migrationen, nachträgliche Verschlüsselung, gezieltes Löschen,
  verschlüsselter Zugangsdatenspeicher (oder System-Schlüsselbund, oder Umgebungsvariablen).
* **Alle zehn Adapter** mit der geforderten Schnittstelle, transparentem Status und konkreten
  Voraussetzungen. ShadowDragon und Babel Street melden „nicht verfügbar (Anbieterzugang)“ –
  ohne erfundene Endpunkte oder Ergebnisse.
* **Graph, Berichte** (Markdown/HTML/JSON/PDF), **JSON-Austauschformat** mit Versionsprüfung und
  ID-Neuvergabe, **CLI** (headless), **PySide6-Oberfläche** mit acht Seiten.
* **AppImage:** Rezept und Buildskript nach den im Quellcode von python-appimage belegten
  Konventionen; Architekturabbruch und Überschreibverbot getestet.
* **Dokumentation:** `PersonIntel/README.md`, `docs/INSTALL.md`, `docs/ARCHITECTURE.md`,
  `docs/FUSION.md`. Ein Test prüft die Dokumentation gegen den Code (API-Namen,
  Aufzählungswerte, Austauschformat, Installationsbefehle).

Belegt durch: 170 Tests, ein Ende-zu-Ende-Durchlauf im installierten Paket (Zweckverweigerung,
Abfrage gegen Werkzeug-Attrappe, Prüfvermerk, Graphregel, Bericht, Export/Import,
Protokollintegrität) sowie Installation in eine frische Umgebung mit beiden Startbefehlen.

## Nicht belegt (fehlende Voraussetzungen, nicht fehlende Umsetzung)

1. **Lauf gegen die echten Werkzeuge.** holehe, mosint, sherlock, phoneinfoga und ignorant waren
   nicht installiert. Getestet wurde gegen ausführbare Attrappen mit den dokumentierten
   Ausgabeformaten. Besonders zu prüfen: das JSON-Schema von Mosint und die Textausgabe der
   PhoneInfoga-CLI – beide sind nicht formal spezifiziert.
2. **Echte Abfragen bei Pipl und Spokeo** (Vertrag, kostenpflichtig). Getestet gegen einen lokalen
   HTTP-Server mit dem dokumentierten Antwortformat.
3. **Der AppImage-Bau selbst.** Er lädt ein Python-Basisimage über die GitHub-Release-API; dieser
   Zugriff war in der Entwicklungsumgebung gesperrt (HTTP 403). Geprüft sind Rezept, Platzhalter,
   Architekturabbruch und Überschreibverbot – nicht der Bau.
4. **Mr.Holmes-Berichte echter Installationen**: der Import ist gegen die Textstruktur geprüft,
   nicht gegen alle Berichtsvarianten.

## Nächste Schritte

1. Auf einem Rechner mit den echten Werkzeugen: `personintel-cli status`, dann je Modul eine
   Abfrage gegen eine eigene Kennung. Abweichungen im Ausgabeformat im jeweiligen Adapter
   (`src/personintel/adapters/<modul>.py`, Methode `normalize_results`) anpassen.
2. AppImage bauen: `pip install python-appimage && apt-get install -y file`, dann
   `PersonIntel/packaging/build_appimage.sh`. Ergebnis landet unter neuem Versionsnamen in
   `DevBuilds/`; bestehende Dateien werden nie überschrieben. ARM64 nur auf ARM64-Hardware oder
   per `docker run --platform linux/arm64` (Befehl steht in `docs/INSTALL.md`).
3. Vor einer Veröffentlichung: Version in `src/personintel/__init__.py` erhöhen.
4. Bei vorliegender Anbieterdokumentation ShadowDragon/Babel Street vervollständigen – nötig sind
   nur `execute_authorized_query` und `normalize_results`; Anleitung in `docs/ARCHITECTURE.md`
   unter „Neuen Anbieter anbinden“.
5. Für die Verschmelzung mit der bestehenden System-OSINT-Anwendung: `docs/FUSION.md`
   (Paket-API `personintel.api`, Austauschformat `personintel.case` 1.0, Entry-Points
   `personintel.adapters` / `personintel.ui_pages`, Einbettung einzelner Oberflächenseiten).

## Flipper-One-Emulator-Tests

Hierzu gibt es **keinen Stand**: in diesen Sitzungen wurden keine Emulator-Tests ausgeführt, und
es liegen keine Ergebnisse oder Logs vor. Das Repository `wasabicover258/Flipper-Emulator` war
nicht angebunden und wurde nicht gelesen. Die vorhandenen FlipperOne-OSINT-AppImages (aarch64,
0.1.1 … 1.3.0) sind unverändert.

Vorschlag für die nächsten Testschritte – bewusst noch nicht durchgeführt:

1. In `Flipper-Emulator` nachsehen, welche Tests und Ergebnisse es für FlipperOne-OSINT 1.3.0 gibt.
2. Klären, ob PersonIntel überhaupt auf Flipper One laufen soll. PySide6/Qt ist für das kleine
   Display und ein ARM64-AppImage schwergewichtig; die Flipper-App ist bewusst Go + SDL2. Für den
   Flipper wäre eher die CLI (`personintel-cli`) oder eine eigene schlanke Oberfläche sinnvoll,
   die über `personintel.api` arbeitet.
3. Falls ja: ARM64-AppImage bauen (Schritt 2 oben), im Emulator starten, Startlog prüfen.
4. Falls nein: PersonIntel nur auf dem Linux-Desktop testen (x86_64 und ARM64).

## Quellen der Schnittstellenrecherche

docs.pipl.com (Search API), docs.spokeo.com (v5), GitHub-READMEs von megadose/holehe,
alpkeskin/mosint, sherlock-project/sherlock, sundowndev/phoneinfoga, megadose/ignorant,
Lucksi/Mr.Holmes; python-appimage.readthedocs.io sowie der Quellcode von
`python_appimage.commands.build.app` für die Rezeptkonventionen.
