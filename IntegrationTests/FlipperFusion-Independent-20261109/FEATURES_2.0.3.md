# FlipperOne-OSINT – ChatGPT Test 2.0.3

## Schöneres Button-Design auf dem Flipper-One-Display

**Ziel:** Listen und Menüeinträge auf dem 256 × 144 Pixel großen Flipper-One-Bildschirm sollen erkennbar **einzelne, bedienbare Buttons** sein. Die monochrome Palette von 2.0.2 bleibt verbindlich: weißer Hintergrund RGB 255, schwarzer Text RGB 0; erst der Emulator färbt die Helligkeiten orange.

### Layout

| Bereich | 2.0.3 |
|---|---|
| Hauptmenü | 6 abgerundete weiße Listenkarten, **1-Pixel-schwarzer Rahmen**, 2 Pixel Abstand |
| Ausgewählter Menüpunkt | **schwarze Fläche und weiße Schrift**, dauerhaft sichtbarer Pfeil `>` |
| Ergebnisübersicht | 8 sichtbare Listenkarten, 12 Pixel Höhe mit 1 Pixel Zwischenraum; per Pfeil / Touch / Scroll erreichbar |
| Untergruppen und Funde | Gleiches Button-Design wie Kategorien; klare Einrückung und ein kleines Statuszeichen |
| Ergebnisanzahlen | Kleine **weiße Zähler-Pills** mit schwarzer Outline (auf ausgewählter Karte klar invertiert) |
| Untere Navigation | Abgerundete Softkeys mit schwarzer Kontur; primäre Aktion schwarz/weiß invertiert |
| Bildschirmüberschrift | Durch 1-Pixel-Trennlinie vom Inhaltsbereich getrennt |
| Bildschirmtastatur | Wie die Listen einheitliche abgerundete Buttons mit invertiertem Fokus |

### Bedienung unverändert

- Pfeiltasten / Mausrad: Auswahl scrollen
- **B** / Enter / Touch: Kategorie oder Fund öffnen
- **X**: eine Ebene zurück
- **Z**: Home
- Wischen in der Ergebnisansicht navigiert jetzt innerhalb der **Kategorien/Untergruppen/Funde**, statt unbeabsichtigt die versteckte Rohdatenliste zu scrollen.

### Farb- und Layoutnachweis

Der Workflow `.github/workflows/experiment-publish-chatgpt-v2.0.3.yml` rendert **neun** reale 256 × 144-SDL2-Bildschirmansichten ohne Emulatorgerät und überprüft:

- jeden einzelnen Pixel auf neutrale Graustufen (`R == G == B`)
- reine Hintergrundpixel mit `R = G = B = 255`
- schwarzen ausgewählten Button und weißen Innenraum eines unselektierten Buttons
- schwarze 1-Pixel-Konturen der Menü- und Kategoriebuttons
- weißen Abstand zwischen den Karten
- Go-Tests und UI-Selbsttest, danach neuen ARM64-AppImage-Build

Zusätzlich lädt der Workflow die gerenderten `*.bmp`-Screenshots als 30 Tage abrufbares Build-Artefakt hoch. Die Bilder stammen aus dem echten SDL2-Renderer. Sie sind **kein** Beweis, dass der externe Flipper-One-Emulator bereits visuell bestätigt wurde.

### Veröffentlichung

`ChatGPT Test/ChatGPT-Test-2.0.3-aarch64.AppImage` in `main`. Die Datei wird nur erstellt, wenn derselbe Name noch nicht existiert. Vorversionen 1.0–2.0.2 bleiben unverändert.

Die Recherchefunktionen, Web-/PDF-Suche und optionale KI-Schnittstelle aus 2.0.1 sind unverändert; 2.0.3 ist ein **rein visuelles UX-Update**.

