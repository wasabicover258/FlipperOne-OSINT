# CONTINUE_DEVELOPMENT – PersonIntel (Zwischenstand)

Stand: 2026-11-08, Sicherung wegen des erreichten Nutzungslimits. **Das ist ein Zwischenstand, keine fertige Version.**

## Wo liegt was

| Was | Wert |
|---|---|
| Repo | `wasabicover258/FlipperOne-OSINT` |
| Branch | `dev/personintel-wip` (neu angelegt; `main` und alle vorhandenen Dateien/AppImages sind unverändert) |
| Basis auf `main` | `4f938ade2339da5d0403b17d5fa9ab3752bbd95d` ("DevBuild AppImage 1.3.0 (aarch64)") |
| Commit-SHA des Code-Snapshots | `e5695f3` ("PersonIntel WIP: Kern, zehn Adapter, Graph, Berichte, Austausch, Tests"); darauf folgt ein zweiter Commit, der nur diese Datei um die SHA ergänzt |
| Projektordner | `PersonIntel/` (eigenständig; berührt `app-ordner/`, `DevBuilds/*.AppImage`, `Public Releases/` nicht) |

Hinweis: PersonIntel ist ein **eigenes Projekt** (Python/PySide6, Linux-Desktop, Personenrecherche mit Zweckprüfung). Es liegt nur deshalb in diesem Repo, weil hier `DevBuilds/` existiert und dies das einzige angebundene Repo war. Die README von FlipperOne-OSINT schließt personenbezogene Dienste (Pipl, Spokeo, ShadowDragon, Babel Street, Mr.Holmes) für die Flipper-App bewusst aus – falls PersonIntel ein eigenes Repo bekommen soll, `PersonIntel/` einfach dorthin verschieben (`git subtree split` oder Kopie).

## Auftrag (Kurzfassung)

Eigenständiges, modulares Linux-Desktop-OSINT-Modul für journalistische Personenrecherche, später mit einem bestehenden System-OSINT-Programm verschmelzbar. Zehn Adapter: Holehe, Mosint, Sherlock, PhoneInfoga, Ignorant, Mr.Holmes, Pipl, Spokeo, ShadowDragon, Babel Street. Pflicht: Belegstufen (unmittelbar belegt / Indiz / unbestätigt), Zweck- und Berechtigungsprüfung je Fall, aktive Prüfungen nur mit gesonderter Bestätigung, lokale (optional verschlüsselte) Speicherung, keine Leak-Passwörter, keine erfundenen Ergebnisse/Endpunkte. Lieferumfang: lauffähiger Code, Tests, Installationsanleitung, AppImage-Buildskript (x86_64 und ARM64), technische Fusionsanleitung. Antworten/UI auf Deutsch.

## Bereits erledigt (alles unter `PersonIntel/src/personintel/`)

- `core/`: Fehler, IDs (präfixiert), Modelle + versioniertes Ergebnisformat, Validierung (genau eine Kennung, E.164), Einstellungen/Pfade, Plugin-Registry (`plugins.py`), Job-Verwaltung (`jobs.py`), Engine-Fassade (`engine.py`).
- `security/`: Autorisierungs-Gate mit HMAC-signierten `AuthorizedQuery` (`authorization.py`), Hash-verketteter Audit-Log ohne Klartext-Kennungen (`audit.py`), Feldverschlüsselung (`crypto.py`), Credential-Store (`credentials.py`).
- `storage/`: SQLite mit Migrationen und optionaler Verschlüsselung, selektives Löschen (`repository.py`, `migrations.py`).
- `adapters/`: alle zehn Adapter mit der geforderten Schnittstelle. Lokale Tools: Holehe, Sherlock, Mosint, PhoneInfoga, Ignorant; Mr.Holmes (Installationserkennung + Berichtsimport); Pipl und Spokeo (HTTP-API); ShadowDragon und Babel Street (nur Konfiguration/Status, Recherche bewusst "nicht verfügbar" – keine öffentliche API-Doku).
- `graph/model.py` (nur manuelle, belegte Kanten; `same_person` nicht allein per Benutzername), `reports/export.py` (Markdown/HTML/JSON), `exchange/schema.py` (JSON-Export/-Import mit Versionsprüfung und ID-Neuvergabe), `api.py` (stabile Fassade), `cli.py` (status, cases, audit-verify, export, import, report), `__main__.py` (startet `personintel.ui.app.run`, **existiert noch nicht**).
- Tests: `tests/conftest.py` (Attrappen-Tools + lokaler Anbieter-HTTP-Server), `tests/test_authorization.py` (13), `tests/test_adapters_local.py` (13). **Stand: `cd PersonIntel && python -m pytest -q` → 26 passed** (Python 3.13, cryptography, phonenumbers, pytest).

## Was getestet ist – und was nicht (ehrlich)

- Getestet gegen **Attrappen-Skripte**, die das dokumentierte Ausgabeformat nachbilden (Holehe-CSV, Sherlock-CSV, Mosint-JSON, PhoneInfoga-CLI und -REST). Die **echten Tools waren im Sandkasten nicht installiert** und sind noch nie gelaufen.
- Ignorant: nur Normalisierung/Rate-Limit-Logik getestet; der Hilfsprozess (`RUNNER_SOURCE`, braucht `ignorant`, `httpx`, `trio`) ist ungetestet.
- Pipl/Spokeo: Code vorhanden, Tests mit lokalem Fake-Server (`FakeVendorServer` in `conftest.py` ist vorbereitet) **noch nicht geschrieben**; echte Anbieter nie angesprochen.
- PhoneInfoga-POST-Schema nicht verifiziert → nur belegte GET-Endpunkte (`/api/v2/scanners`, `scan/local`, `scan/googlesearch`) plus CLI-Fallback.
- UI: **nicht begonnen.** AppImage: **nicht gebaut.**

## Flipper-One-Emulator-Tests – Stand

- In dieser Sitzung wurden **keine** Flipper-One-Emulator-Tests ausgeführt, und es gibt dazu keine Ergebnisse, Logs oder Notizen, die ich dokumentieren könnte. Ich erfinde hier nichts.
- Auf dem GitHub-Konto existiert `wasabicover258/Flipper-Emulator` (zuletzt gepusht 2026-11-08 12:36 UTC); es war in dieser Sitzung **nicht angebunden und nicht gelesen**. Der Stand der Emulator-Tests muss dort bzw. in `FlipperOne-OSINT` (`VERSIONS.md`, Workflow `.github/workflows/build-appimage.yml`) nachgesehen werden.
- Vorhandene FlipperOne-OSINT-AppImages (aarch64, 0.1.1 … 1.3.0) wurden **nicht verändert**.
- Nächste Testschritte (Vorschlag, noch nicht durchgeführt): (1) in `Flipper-Emulator` nachsehen, welche Tests/Ergebnisse es für FlipperOne-OSINT 1.3.0 gibt; (2) klären, ob PersonIntel überhaupt auf Flipper One laufen soll (PySide6 + Qt ist für das kleine Display und ARM64-AppImage schwergewichtig; die Flipper-App ist bewusst Go+SDL2); (3) falls ja: ARM64-AppImage von PersonIntel bauen (siehe unten) und im Emulator starten, Startlog prüfen; (4) falls nein: PersonIntel nur auf Linux-Desktop (x86_64/ARM64) testen.

## Offene Punkte / bekannte Lücken

1. Tests ergänzen: Audit-Manipulation (`audit.verify`/`rechain`), Storage (Migration, Verschlüsselung, `delete_case`, `encrypt_existing`), Credentials (Locked, Env-Override, 0600), Pipl/Spokeo (Fake-Server: Schlüssel ungültig → 403 → Status `ERROR`, Datenminimierung: keine Adressen/DOB/Verwandte), Vendor-Contract (ShadowDragon/Babel Street → `AuthorizationDenied`), Graph-Regeln, Exchange (Roundtrip, Versionssperre, ID-Neuvergabe), Report (HTML-Escaping), Plugin-Registry, CLI.
2. UI mit PySide6 (`src/personintel/ui/`, Einstiegspunkt `ui/app.py: run(args) -> int`): Dashboard (Echtstatus der zehn Module), Fälle (Zweck, Kennungen), Recherche-Formulare mit Bestätigungsdialog für aktive Prüfungen, Ergebnisse (Quelle, Zeitstempel, Belegstufe, Prüfstatus), Graph (`graph.model.layout`), Zeitleiste (`Engine.timeline`), Bericht (MD/HTML/PDF), Einstellungen (pro Adapter aus `Adapter.config_fields`, Zugangsdaten entsperren, Pipl `test_connection()`), Fall-Import/-Export, Löschen. Job-Updates per `engine.jobs.add_listener` über Qt-Signal in den GUI-Thread bringen. Offscreen-Smoketest mit `QT_QPA_PLATFORM=offscreen` (`pip install PySide6 --break-system-packages`).
3. Packaging: `packaging/build_appimage.sh` + `packaging/appimage/{entrypoint.sh,requirements.txt,personintel.desktop,icon}` (python-appimage; ARM64 nur auf nativer ARM64-Hardware oder per QEMU mit `--linux-tag manylinux2014_aarch64`). Ausgabe **nur** nach `DevBuilds/PersonIntel-<neue-Version>-<arch>.AppImage`, nie bestehende Dateien überschreiben; `DevBuilds/VERSIONS.md` nur durch Anfügen einer neuen Zeile ändern. Bisher **kein** Build.
4. Dokumentation: `README.md`, `docs/INSTALL.md`, `docs/ARCHITECTURE.md` (inkl. "Neuen Anbieter anbinden"), `docs/FUSION.md` (Paket-API `personintel.api`, Austauschformat `personintel.case` 1.0, Plugin-Entry-Points `personintel.adapters`/`personintel.ui_pages`). `docs/` und `packaging/appimage/` sind leer.
5. Echte Tools verifizieren, sobald installiert: `holehe`, `sherlock`, `mosint` (+ `~/.mosint.yaml`), `phoneinfoga`, `ignorant`; erst dann Annahmen zu Ausgabeformaten bestätigen (insbesondere Mosint-JSON-Schema und PhoneInfoga-CLI-Text, beides nicht formal dokumentiert).
6. `pyproject.toml` verweist auf `personintel.__main__:main` und `personintel.cli:main` – beide vorhanden; `ui.app` fehlt noch.
7. ShadowDragon/Babel Street: Recherche bleibt "nicht verfügbar", bis Anbieterdokumentation, Basis-URL, Authentifizierung und Antwortschema vorliegen (Voraussetzung steht im jeweiligen Adapter in `REQUIREMENT`).

## Exakte nächste Schritte

```bash
git clone https://github.com/wasabicover258/FlipperOne-OSINT && cd FlipperOne-OSINT
git checkout dev/personintel-wip
cd PersonIntel
pip install -e '.[dev]' --break-system-packages     # cryptography, phonenumbers, pytest
python -m pytest -q                                  # erwartet: 26 passed
```

1. Fehlende Tests schreiben (Punkt 1) und grün bekommen.
2. `pip install PySide6 --break-system-packages`, `src/personintel/ui/` bauen (Punkt 2), Offscreen-Smoketest.
3. Docs schreiben (Punkt 4).
4. AppImage-Skript schreiben (Punkt 3), auf Zielhardware bauen, Ergebnis unter neuem Versionsnamen in `DevBuilds/` ablegen.
5. Flipper-One-Emulator-Abschnitt oben abarbeiten.
6. Abschlussbericht mit klarer Trennung "verifiziert / unverifiziert".

## Quellen der Schnittstellenrecherche

docs.pipl.com (Search API), docs.spokeo.com (v5), GitHub-READMEs von megadose/holehe, alpkeskin/mosint, sherlock-project/sherlock, sundowndev/phoneinfoga, megadose/ignorant, Lucksi/Mr.Holmes.
