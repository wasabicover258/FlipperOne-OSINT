# ChatGPT Test 1.6.1 – Zuverlässigkeitsergänzung

**Basis:** `ChatGPT Test 1.6`, alle bisherigen Recherchepfade und die strikte Sortierung nach Entfernung bleiben erhalten.

## Warum diese Version nötig wurde

Der separate ARM64-Live-Test von 1.6 hat **8 von 10** abgefragten öffentlichen Datenquellen mit nutzbarem JSON bestätigt. Zwei Datenquellen waren nicht rechtzeitig erreichbar:

- RIPEstat Routing-Status (Timeout nach 4,5 Sekunden)
- Overpass-API für die Umgebungssuche (Timeout nach 18 Sekunden)

Ein erfolgreicher Offline-Test kann solche Server-Ausfälle nicht ausschließen.

## Korrektur

- Primärer Ortssuchendpunkt: **overpass.private.coffee** (nicht-kommerzieller OpenStreetMap-Server von Private.coffee, 2026 öffentlich dokumentiert).
- Alternativer Endpunkt: **overpass-api.de**.
- Wenn die erste Abfrage scheitert, wird der zweite Server **einmalig** mit derselben Radiusabfrage versucht. Pro Server gilt ein 11-Sekunden-Timeout. Kein unbegrenztes Retry.
- Live-Antworten werden weiterhin identisch dedupliziert, strikt aufsteigend nach Entfernung sortiert und mit OSM-Quelle angezeigt.
- Separater Regressionstest `TestPOIAlternateProviderAfterFailure`: 429 beim ersten HTTP-Dienst, erfolgreiche Klinik-/Restaurant-Antwort vom zweiten.
- RIPEstat Routing-Status darf bis zu 9 Sekunden dauern, bleibt aber ein optionaler Zusatz.
- Historische `http://web.archive.org/`-Links werden auf `https://web.archive.org/` normalisiert, nur für diesen fest erwarteten Anbieter.

## Unveränderte Betriebsgrenzen

- Maximal 28 angezeigte Einrichtungen aus der verfügbaren Overpass-Antwort. Bei hoher Dichte ist das keine Garantie einer vollständigen Liste sämtlicher Betriebe.
- Öffentliche OpenStreetMap-Daten können fehlen oder veraltet sein.
- Keine automatische Identitätsverkettung oder private Kontakt-Ermittlung.
- Die externe Python-Runtime und proprietäre PersonIntel-Zugänge sind weiterhin nicht automatisch im AppImage enthalten.
- Ein grüner ARM64-Build beweist noch keinen erfolgreichen Start in deinem Windows-Flipper-One-Emulator.

## Tests

- Native ARM64-Paketierung und Go-Tests in `experiment-publish-chatgpt-v1.6.1.yml`.
- Neuer Offline-Fallbacktest.
- Gesonderter optionaler ARM64-Livetest `experiment-chatgpt-v1.6.1-live.yml`.
- Die AppImage erscheint ausschließlich als neuer Dateiname `ChatGPT Test/ChatGPT-Test-1.6.1-aarch64.AppImage`; ältere Versionen werden nicht überschrieben.

Dokumentation der anderen 16 Rechercheverbesserungen: `FEATURES_1.6.md`.
