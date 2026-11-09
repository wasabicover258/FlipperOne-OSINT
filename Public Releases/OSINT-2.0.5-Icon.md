# OSINT 2.0.5 – Flipper App-Shelf-Icon

**ARM64-Download:** `FlipperOne-OSINT-2.0.5-aarch64.AppImage`

Ausschließlich das App-Shelf-Icon wurde korrigiert. Alle OSINT-Suchfunktionen und die Bedienoberfläche entsprechen Version 2.0.4.

- `app.toml` in der SquashFS-Wurzel: `name = "OSINT"`, `icon = "flipperone-osint.png"`
- `flipperone-osint.png` direkt daneben, exakt die vom Nutzer bereitgestellte 14 × 14 RGBA-Pixel-Lupe
- Alpha-Kanal nur 0 oder 255, 156 transparente Hintergrundpixel und 40 deckende Symbolpixel
- Altes großes Ersatzicon entfernt
- ARM64, 343 UI-Prüfungen, alle Go-Tests und Extraktion des fertig gebauten AppImage erfolgreich
- SHA-256: `5d1568fb1170bc491c02f4d4d36ade7eec426e46c7e83352c1b0945702f3bbc1`

**Emulator:** Nach Installation/Neuladen sollte im App Shelf eine Lupe statt des schwarzen Quadrats erscheinen. Diese Darstellung muss im echten Flipper-Emulator noch visuell geprüft werden.

Build: https://github.com/wasabicover258/FlipperOne-OSINT/actions/runs/42683024791

Diese Release-Notiz löst außerdem die automatische Synchronisation der neuesten ARM64-AppImage ins Flipper-Emulator-AppCatalogue aus.
