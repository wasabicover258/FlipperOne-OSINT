# FlipperOne-OSINT + PersonIntel – Stand der Entwicklung

Letzte Aktualisierung: 2026-11-09. Diese Datei ist der Wiedereinstiegspunkt: Stand, Belege,
offene Punkte und die nächsten Schritte. Sie ersetzt den Stand vom 08.11. (reines PersonIntel).

| | |
|---|---|
| Repo | `wasabicover258/FlipperOne-OSINT` |
| Branch | `fusion/flipper-personintel` – `main` ist unverändert |
| Letzter Build | `DevBuilds/FlipperOne-OSINT-1.4.1-aarch64.AppImage` (3.078.664 Bytes) |
| SHA-256 | `d0dc477c72c08e3ef4c085acb7e63fc0dbe1c95da65944843fba36a1325f98d5` |
| Build-Commit | `4efb6d4` (Workflow-Lauf 42610680908, erfolgreich) |
| Tests | 195 Python, 15 Go, 168 Selbstprüfungen der Oberfläche – gezählt, nicht geschätzt |
| Workflow | `.github/workflows/build-appimage-fusion.yml` (nur `fusion/**`, schreibt nie nach `main`) |

Alle 16 älteren AppImages sind unverändert. `Public Releases/` wurde nicht angefasst.

## Was die Fusion ist

Eine App: die bestehende leichte SDL2-Oberfläche (256×144, Flipper-Tasten Z X C V B) mit
statischem Go-Backend, dazu PersonIntel als reines Python-Paket im Bundle unter
`usr/lib/personintel` (540 KB). Die Oberfläche spricht über eine kurzlebige NDJSON-Brücke mit
dem Python-Teil; PySide6 ist bewusst nicht dabei (≈250 MB, für das Display sinnlos).

`cryptography` und `phonenumbers` liegen absichtlich **nicht** im Bundle (keine
interpreterunabhängigen Wheels bzw. 24 MB Metadaten). Beide werden erst bei Bedarf importiert;
fehlen sie, meldet das Modul die Voraussetzung, statt zu scheitern.

## Belegt

* 195 Python-, 15 Go-Tests und 168 Selbstprüfungen der Oberfläche, alle grün.
* Der Abschlusstest im Workflow prüft drei Umgebungen: ohne `cryptography`/`phonenumbers`,
  ohne jeden Python-Interpreter (`PATH=/nonexistent`) und mit vollständiger Umgebung. Geprüft
  werden Modulstatus, Zweck-Sperre, Verweigerung ohne Bestätigung, Lauf mit Bestätigung sowie
  Beleggrad und Version im Ergebnis.
* Der Build läuft auf `ubuntu-24.04-arm`; ein Bau für die falsche Architektur ist unmöglich
  (`platform.machine()` bestimmt den Namen).
* Address- und UB-Sanitizer über die Oberfläche (Selbsttest und alle sieben gerenderten
  Bildschirme): ohne Befund.

## Nachgewiesen im Flipper-One-Emulator (2026-11-09)

Zugang: Flipper OS auf `127.0.0.1:8930`, File Manager auf `127.0.0.1:8898`, beides über den
Browser des Nutzers. Tastendrücke gehen per `POST /input`, Bilder kommen über `GET /stream`
(8-Byte-Kopf x,y,w,h + w*h Graustufenbytes; Nullfläche = Keepalive).

| Beobachtung | Ergebnis |
|---|---|
| 1.4.1 installiert, Datei im Gast zurückgelesen | SHA-256 stimmt mit dem Build überein |
| **OSINT 1.3.0 starten** | **läuft** – Menü sichtbar, 23 Bildaktualisierungen |
| **Native Hello starten** | **läuft** – Tastendrücke erhöhen den Zähler nachweislich |
| **OSINT 1.4.1 starten** | **startet nicht** – kein einziges Bild, auch nach 3 Minuten; 3 Versuche |
| Python 3 im Gast | **nicht vorhanden** – „Python Runtime" (30 MB) steht im Katalog als *nicht installiert* |

Ausgeschlossen als Ursache für den Fehlstart: Bibliotheksabhängigkeiten und glibc-Versionen
(identisch zu 1.3.0), Symbolversionen, Kompression, Blockgröße und Struktur des Abbilds,
Dateirechte, Speicherfehler im C-Code, Compiler- und Linkerflags (beide Workflows identisch),
sowie Geduld (Software-Emulation ist langsam, das erklärt es nicht).

**Wichtige Lehre:** eigene Umpackversuche (`1.4.2-diag`, `1.4.3-diag2`, `1.3.0-diag3`) sind als
Diagnosemittel unbrauchbar. Auch die *unveränderte* 1.3.0, mit demselben Verfahren neu gepackt,
startet nicht – das Umpacken selbst ist die Ursache, vermutlich das Längen-/Offsetfeld im
AppImage-Runtime. Nur über `appimagetool` im Workflow gebaute Bundles sind aussagekräftig.

## Offen

1. **Fehlstart von 1.4.1** – die Ursache steht im Startprotokoll der App, das im Gast unter
   `/tmp/flipperone-osint.log` liegt und von außen nicht lesbar ist. Deshalb kopiert AppImage
   `1.4.4-diag` dieses Protokoll bei einem Fehlstart nach `/home/user/Files`, wo der File
   Manager es anzeigt. Bei erfolgreichem Start wird dort nichts abgelegt.
2. **Testbericht** `DevBuilds/EMULATOR_TEST_1.4.1.md` (30 Schritte) ist noch nicht abgearbeitet,
   weil die App nicht startet. Die Schritte 1–4 (Bestand, Navigation) sind über 1.3.0 belegt.
3. **PersonIntel-Brücke auf dem Gerät** kann ohne Python nicht starten. Zu klären ist, ob die
   „Python Runtime" aus dem Katalog `python3` so bereitstellt, dass die Brücke sie findet.

## Nächste Schritte

1. `1.4.4-diag` im Emulator installieren, starten, `/home/user/Files/flipperone-osint-start.log`
   über den File Manager lesen. Dort steht die echte Fehlermeldung samt Exit-Code und – als
   direkter Beleg für Punkt 3 – ob `python3` im Gast gefunden wird.
2. Den nachgewiesenen Fehler beheben, Version in `app-ordner/VERSION` erhöhen, bauen lassen.
   Der Workflow bricht ab, wenn die Zieldatei schon existiert; alte Dateien bleiben dadurch
   unberührt.
3. `EMULATOR_TEST_1.4.1.md` mit den tatsächlichen Ergebnissen füllen, danach `FUSION_1.4.1.md`.
4. AppRun vor dem Abschluss prüfen: es ersetzt sich für die Diagnose nicht mehr per `exec`
   durch `osint-ui`. Falls das bleibt, ist es bewusst zu dokumentieren.

## Arbeitsregeln für diesen Zweig

* Keine Änderungen an `main`, keine vorhandene AppImage-Datei überschreiben, löschen oder
  ersetzen. Neue Builds ausschließlich unter neuem Versionsnamen in `DevBuilds/`.
* Keine simulierten Rechercheergebnisse als Nachweis echter Funktionalität.
* Nach jedem abgeschlossenen Schritt ein Commit und ein Push.
