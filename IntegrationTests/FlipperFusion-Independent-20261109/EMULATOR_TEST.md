# Verbindlicher A/B-Test – Flipper One

**Zwei unabhängige AppImages, beide frisch installiert über denselben File Manager.**
Referenz: `OSINT LAB CONTROL` (Quellcode `main`, Version 1.3.0).
Fusion: `OSINT LAB FUSION` (Quellcode `fusion/flipper-personintel`).

Dieser Test darf nicht mit einer bereits früher installierten 1.3.0 verwechselt werden.

## Vorbereitung

- Windows-Helfer im Modus **Flipper OS + File Manager** öffnen.
- Beide frisch gebauten LAB-AppImages aus dem GitHub-Workflow herunterladen.
- Jede Datei anhand der jeweiligen SHA-256-Datei verifizieren.
- Mit dem File Manager beide hochladen und installieren (verschiedene App-Titel).
- **Keinen Factory Reset** durchführen. Vorhandene AppImages und Daten nicht löschen.
- Vor Startprüfung den realen Flipper-OS-Gast einmal regulär neu starten, damit eine eventuell erforderliche Neuregistrierung für beide gleich abläuft.

## Vergleich

| Prüfung | CONTROL | FUSION |
|---|---|---|
| Beide App-Einträge nach Neustart sichtbar | offen | offen |
| App startet mit sichtbarem Menü | offen | offen |
| D-Pad/OK/Back bedienbar | offen | offen |
| `Phone number` offline, `0171 1234567` | offen | offen |
| `Domain` mit ausdrücklich autorisiertem Testziel | optional | optional |
| Stabilität nach erneutem Start | offen | offen |

Falls beide starten: bei **FUSION** zusätzlich `Person modules` öffnen. Erwartet ist entweder korrekter Modulstatus oder eine klare Warnung, dass `python3 >= 3.10` fehlt. Keine externen Personenrecherchen automatisiert ausführen.

## Ergebnislogik

- **Beide neu installierten Images scheitern**, aber die alte bereits installierte App startet: zunächst File-Manager-Installationspfad/App-Registry/OS-Neustart prüfen. **Noch keine Fusion als Ursache behaupten.**
- **Nur CONTROL startet**: Fusion oder Paketinhalt verursacht eine Regression, gezielt Code-/Runtime-Differenzen analysieren.
- **Beide starten**: Die reine Startfähigkeit der Fusion ist bestätigt, PersonIntel-Bridge und externe Abhängigkeiten sind **separat** zu prüfen.
- **Nur FUSION startet**: Die ursprüngliche Kontrollannahme stimmt in dieser Umgebung nicht; Logs sichern.

## Artefakte zur Beweissicherung

- AppImage-Dateiname, SHA-256 und CI-Link
- Emulatorversion, Flipper-OS-Image-Version
- Zeitpunkt des OS-Neustarts
- Installationsweg beider Images
- Exakte Fehlermeldungen und Startlog `/tmp/flipperone-osint.log`
- Screenshot des Menüs pro Variante
- Ob `python3 --version` im Gast erfolgreich ist

**Keine der Varianten gilt allein wegen eines grünen GitHub-Actions-Builds als emulatorgetestet.**
