# FlipperOne-OSINT – isolierter Integrationsversuch (2026-11-09)

**Ziel:** Keine weiteren Umbauten an der bestehenden Anwendung. In genau derselben ARM64-Buildumgebung werden zwei AppImages erzeugt:

| Variante | Quellen | Zweck |
|---|---|---|
| **CONTROL** | unveränderte Dateien aus `origin/main` (Version 1.3.0) | bekannte, zuvor funktionierende Referenz |
| **FUSION** | Quellen des Experiment-Branches (abgezweigt von `fusion/flipper-personintel`) | bestehende PersonIntel-Integration unverändert testen |

Beide Builds verwenden **denselben Compiler, dasselbe appimagetool, dieselben Einstellungen und denselben Installationsweg**. Die beiden neu gebauten AppImages erhalten eindeutige Anwendungsnamen (OSINT Lab Control / OSINT Lab Fusion). Keine bisherige AppImage wird verändert. Der Unterschied ist nur der jeweilige Quellcode einschließlich des vorhandenen PersonIntel-Adapters.

## Dateien

- `build_arm64.sh`: reproduzierbarer Doppelbuild für ARM64. Erstellt zwei neue AppImages unter `artifacts/` und SHA-256-Dateien.
- `EMULATOR_TEST.md`: kontrollierter A/B-Test mit identischem Installationsweg und Neustartbedingung.
- `.github/workflows/experiment-isolated-fusion.yml`: separater ARM64-CI-Workflow für **nur diesen** Experiment-Branch, mit Artefakt-Upload; überschreibt keine Dateien unter `DevBuilds/`, `Public Releases/` oder auf `main`.

## Abgrenzung

Diese beiden Images sind **Diagnose-Builds**, keine Behauptung, dass PersonIntel bereits auf Flipper OS funktioniert. Das PersonIntel-Paket ist in der Fusionsvariante weiterhin reiner Python-Code. Ohne `python3 >= 3.10` auf dem Zielsystem werden die Person-Connectoren korrekt als nicht verfügbar angezeigt. Die externen OSINT-Programme und kommerziellen API-Lizenzen sind ebenfalls **nicht** enthalten. Der Build beweist Architektur und Packaging, nicht die Funktionsfähigkeit echter Provider-Abfragen.

## Ergebnisentscheidung

1. CONTROL startet **nicht**, FUSION startet nicht: zunächst Emulator-Installation/Registrierung/Startpfad untersuchen. Nicht weiter die Fusionsquellen verändern.
2. CONTROL startet, FUSION startet **nicht**: eine Regression in der Fusion oder deren Paketinhalt ist plausibel. Differenzierte Startlogs und minimalen Codevergleich auswerten.
3. Beide starten: bestehende Module prüfen, anschließend Python-Laufzeit und PersonIntel-Brücke gezielt freigeben und testen.
4. Erst wenn kontrollierter Emulatorstart und Basisfunktionen nachgewiesen sind, neue Integrationsänderungen anfertigen.

## Build

Auf einem ARM64-Linux-System (oder ARM64-GitHub-Runner) mit Go, GCC, SDL2-Entwicklerbibliothek, `readelf`, `git` und `appimagetool`:

```bash
APPIMAGETOOL=/pfad/zu/appimagetool ./IntegrationTests/FlipperFusion-Independent-20261109/build_arm64.sh
```

Der CI-Workflow erstellt die ausführbaren Dateien automatisch, sofern die Abhängigkeiten und GitHub Actions verfügbar sind.

**Datenschutz:** Die Tests verwenden ausschließlich offline auswertbare Testeingaben. Es finden keine automatisierten Personenabfragen, keine unkontrollierten Profil-Pivots und keine Kontakte zu kommerziellen Anbietern statt.
